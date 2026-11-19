from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import hashlib
import json
import os
from groq import Groq
from inference import evaluar_sintomas
from database import get_db_connection

# Leemos la clave de la API de Groq desde las variables de entorno para no dejarla escrita en el código
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)

# Inicializamos las tablas en la base de datos automáticamente cuando arranca el servidor
def inicializar_bd():
    conn = get_db_connection()
    if conn is None:
        print("Advertencia: No se pudo conectar a la BD al iniciar.")
        return
    try:
        cursor = conn.cursor()
        # Creamos la tabla de usuarios si todavía no existe en el servidor
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id_usuario INT AUTO_INCREMENT PRIMARY KEY,
                cedula VARCHAR(20) NOT NULL UNIQUE,
                nombres VARCHAR(100) NOT NULL,
                apellidos VARCHAR(100) NOT NULL,
                contrasena VARCHAR(255) NOT NULL,
                pin_seguridad VARCHAR(4) NOT NULL DEFAULT '0000',
                fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        # Creamos la tabla de evaluaciones relacionada con cada usuario
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evaluaciones (
                id_evaluacion INT AUTO_INCREMENT PRIMARY KEY,
                id_usuario INT NOT NULL,
                s_disuria TINYINT(1) NOT NULL DEFAULT 0,
                s_hematuria TINYINT(1) NOT NULL DEFAULT 0,
                s_fiebre TINYINT(1) NOT NULL DEFAULT 0,
                s_polaquiuria TINYINT(1) NOT NULL DEFAULT 0,
                s_dolor_lumbar TINYINT(1) NOT NULL DEFAULT 0,
                nivel_riesgo VARCHAR(50) NOT NULL,
                recomendacion TEXT NOT NULL,
                color_riesgo VARCHAR(20) NOT NULL,
                fecha_evaluacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT evaluaciones_ibfk_1 FOREIGN KEY (id_usuario)
                    REFERENCES usuarios (id_usuario) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        # Insertamos el usuario Demo por defecto (cédula 000) si aún no está creado
        cursor.execute("""
            INSERT IGNORE INTO usuarios (id_usuario, cedula, nombres, apellidos, contrasena, pin_seguridad)
            VALUES (5, '000', 'Usuario', 'Demo', '2ac9a6746aca543af8dff39894cfe8173afba21eb01c6fae33d52947222855ef', '0000');
        """)
        conn.commit()
        print("Base de datos verificada e inicializada correctamente.")
    except Exception as e:
        print(f"Error inicializando tablas: {e}")
    finally:
        cursor.close()
        conn.close()

# Aquí configuramos el ciclo de vida de la app para que revise las tablas apenas inicie
@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_bd()
    yield

# Definimos la estructura de datos que esperamos extraer del paciente
class SintomasExtraidos(BaseModel):
    s_disuria: bool = Field(description="true si el paciente menciona tener dolor, ardor o molestias al orinar.")
    s_hematuria: bool = Field(description="true si el paciente menciona haber notado sangre en la orina.")
    s_fiebre: bool = Field(description="true si el paciente menciona tener fiebre, calentura o escalofríos.")
    s_polaquiuria: bool = Field(description="true si el paciente menciona orinar con mucha más frecuencia de lo normal.")
    s_dolor_lumbar: bool = Field(description="true si el paciente menciona dolor en la parte baja de la espalda o riñones.")
    respuesta_chat: str = Field(description="Mensaje empático validando síntomas. Máximo 3 líneas.")
    hay_sintomas: bool = Field(description="true si el usuario menciona algún síntoma físico o malestar, false si es solo un saludo o charla general.")

# Este es el prompt principal que guía el comportamiento de nuestro asistente médico
PROMPT_SISTEMA = """Eres el orientador médico de UroTriaje. Recibirás el historial completo de la conversación con el paciente.
REGLAS VITALES Y ALCANCE (¡MUY IMPORTANTE!):
1. Eres una herramienta de ORIENTACIÓN PRELIMINAR y TRIAJE DIGITAL, NO eres un médico. ESTÁ ESTRICTAMENTE PROHIBIDO emitir diagnósticos médicos, recetar medicamentos o invalidar la consulta presencial.
2. Actúa de forma MUY EMPÁTICA, cálida y humana.
3. NO uses terminología médica compleja en tu respuesta. Usa lenguaje natural y sencillo.
4. REGLA DE CHARLA INICIAL: Si el usuario SÓLO te saluda (ej. "hola", "buenos días", "cómo estás") o no describe ningún síntoma o malestar, establece 'hay_sintomas' en false, marca todos los síntomas urológicos en false, y en 'respuesta_chat' devuélvele el saludo amablemente preguntándole: "¿Cómo te puedo ayudar hoy? Por favor, cuéntame qué malestares sientes."
5. REGLA DE TRIAJE: Si el usuario menciona malestares físicos, dolor o síntomas médicos, establece 'hay_sintomas' en true. Evalúa la historia clínica total para extraer los 5 síntomas de alarma como booleanos.
6. SOLO SI HAY SÍNTOMAS ('hay_sintomas': true), termina tu mensaje 'respuesta_chat' indicando: "He procesado tu información para darte una orientación preliminar sobre tu nivel de riesgo:"

DEBES responder ÚNICAMENTE con un objeto JSON estricto con esta estructura:
{
  "s_disuria": boolean,
  "s_hematuria": boolean,
  "s_fiebre": boolean,
  "s_polaquiuria": boolean,
  "s_dolor_lumbar": boolean,
  "hay_sintomas": boolean,
  "respuesta_chat": "Tu respuesta empática y humana (Máx 4 líneas)."
}
"""

# Inicializamos la aplicación principal de FastAPI
app = FastAPI(
    title="API UroTriaje Híbrido",
    description="Backend con Estado Acumulado",
    lifespan=lifespan
)

# Configuramos CORS para permitir que nuestro frontend en la web se comunique con la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ruta sencilla para comprobar que el servidor está encendido y respondiendo
@app.get("/")
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "UroTriaje API"}

# Función de seguridad básica para no guardar contraseñas en texto plano
def hashear_contrasena(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Aquí definimos los modelos de datos que vamos a recibir desde Flutter
class RegistroRequest(BaseModel):
    cedula: str
    nombres: str
    apellidos: str
    contrasena: str
    pin_seguridad: str

class LoginRequest(BaseModel):
    cedula: str
    contrasena: str

class RecuperarRequest(BaseModel):
    cedula: str
    pin_seguridad: str
    nueva_contrasena: str

class ChatEvaluacionRequest(BaseModel):
    id_usuario: int
    mensaje_usuario: str
    sintomas_previos: dict

# Endpoint para registrar un nuevo usuario en la base de datos
@app.post("/api/registro")
def registrar_usuario(req: RegistroRequest):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a BD")
    try:
        cursor = conn.cursor()
        # Primero validamos que la cédula no esté ya registrada
        cursor.execute("SELECT id_usuario FROM usuarios WHERE cedula = %s", (req.cedula,))
        if cursor.fetchone() is not None:
            raise HTTPException(status_code=400, detail="Cédula ya registrada")

        # Ciframos la contraseña y guardamos el nuevo usuario con su PIN
        pass_hash = hashear_contrasena(req.contrasena)
        cursor.execute(
            "INSERT INTO usuarios (cedula, nombres, apellidos, contrasena, pin_seguridad) VALUES (%s, %s, %s, %s, %s)",
            (req.cedula, req.nombres, req.apellidos, pass_hash, req.pin_seguridad)
        )
        conn.commit()
        return {"status": "success", "id_usuario": cursor.lastrowid, "nombres": req.nombres}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# Endpoint para validar el acceso de un usuario existente
@app.post("/api/login")
def iniciar_sesion(req: LoginRequest):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de BD")
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_usuario, nombres, contrasena FROM usuarios WHERE cedula = %s", (req.cedula,))
        usuario = cursor.fetchone()

        # Validamos que el usuario exista y que la contraseña coincida con el hash guardado
        if not usuario or usuario["contrasena"] != hashear_contrasena(req.contrasena):
            raise HTTPException(status_code=401, detail="Cédula o clave incorrecta")
        return {"status": "success", "id_usuario": usuario["id_usuario"], "nombres": usuario["nombres"]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# Endpoint para permitir al usuario cambiar su contraseña si la olvidó, usando su PIN de seguridad
@app.post("/api/recuperar_password")
def recuperar_password(req: RecuperarRequest):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de conexión a BD")
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_usuario, pin_seguridad FROM usuarios WHERE cedula = %s", (req.cedula,))
        usuario = cursor.fetchone()

        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        # Verificamos que el PIN ingresado sea el mismo que registró el usuario
        if usuario["pin_seguridad"] != req.pin_seguridad:
            raise HTTPException(status_code=401, detail="El PIN de seguridad es incorrecto")

        # Actualizamos la clave con el nuevo hash en la base de datos
        nuevo_hash = hashear_contrasena(req.nueva_contrasena)
        cursor.execute("UPDATE usuarios SET contrasena = %s WHERE cedula = %s", (nuevo_hash, req.cedula))
        conn.commit()
        return {"status": "success", "message": "Contraseña actualizada exitosamente"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# Aquí es donde ocurre el proceso principal: analizamos el mensaje del paciente con la IA para extraer síntomas
@app.post("/api/chat_evaluar")
def procesar_chat_evaluacion(req: ChatEvaluacionRequest):
    try:
        # Hacemos la consulta a Groq pasándole las instrucciones y el mensaje del usuario
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": req.mensaje_usuario}
            ],
            model="openai/gpt-oss-20b",
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        texto_limpio = chat_completion.choices[0].message.content.strip()
        datos_extraidos = json.loads(texto_limpio)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"La IA tuvo un problema: {str(e)}")

    hay_sintomas_ahora = datos_extraidos.get("hay_sintomas", False)
    tenia_sintomas_antes = any(req.sintomas_previos.values())

    # Si el usuario solo está saludando o hablando sin describir síntomas, le pedimos más detalles
    if not hay_sintomas_ahora and not tenia_sintomas_antes:
        return {
            "status": "success",
            "data": {
                "mensaje_chat": datos_extraidos.get("respuesta_chat", "Hola, ¿en qué te puedo ayudar hoy?"),
                "evaluacion": {
                    "nivel_riesgo": "Esperando síntomas...",
                    "recomendacion": "Por favor describe tus molestias para que pueda orientarte.",
                    "color_riesgo": "#808080"
                },
                "sintomas_acumulados": req.sintomas_previos
            }
        }

    # Consolidamos los síntomas: si la IA detectó un síntoma ahora, o si ya lo traíamos de antes, se marca como true
    sintomas_finales = {
        "s_disuria": req.sintomas_previos.get("s_disuria", False) or datos_extraidos.get("s_disuria", False),
        "s_hematuria": req.sintomas_previos.get("s_hematuria", False) or datos_extraidos.get("s_hematuria", False),
        "s_fiebre": req.sintomas_previos.get("s_fiebre", False) or datos_extraidos.get("s_fiebre", False),
        "s_polaquiuria": req.sintomas_previos.get("s_polaquiuria", False) or datos_extraidos.get("s_polaquiuria", False),
        "s_dolor_lumbar": req.sintomas_previos.get("s_dolor_lumbar", False) or datos_extraidos.get("s_dolor_lumbar", False),
    }

    try:
        # Con los síntomas consolidados, llamamos a nuestro motor de inferencia para calcular el riesgo
        resultado_riesgo = evaluar_sintomas(
            sintomas_finales["s_disuria"],
            sintomas_finales["s_hematuria"],
            sintomas_finales["s_fiebre"],
            sintomas_finales["s_polaquiuria"],
            sintomas_finales["s_dolor_lumbar"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el motor experto: {str(e)}")

    # Guardamos en la base de datos la evaluación resultante junto con los síntomas reportados
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de BD")
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO evaluaciones 
            (id_usuario, s_disuria, s_hematuria, s_fiebre, s_polaquiuria, s_dolor_lumbar, nivel_riesgo, recomendacion, color_riesgo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        valores = (
            req.id_usuario,
            sintomas_finales["s_disuria"],
            sintomas_finales["s_hematuria"],
            sintomas_finales["s_fiebre"],
            sintomas_finales["s_polaquiuria"],
            sintomas_finales["s_dolor_lumbar"],
            resultado_riesgo["nivel_riesgo"],
            resultado_riesgo["recomendacion"],
            resultado_riesgo["color_riesgo"]
        )
        cursor.execute(query, valores)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Error guardando evaluación")
    finally:
        cursor.close()
        conn.close()

    # Le devolvemos al frontend tanto el mensaje amigable de la IA como el resultado técnico de la evaluación
    return {
        "status": "success",
        "data": {
            "mensaje_chat": datos_extraidos.get("respuesta_chat", "He procesado tus síntomas y analizado tu riesgo:"),
            "evaluacion": resultado_riesgo,
            "sintomas_acumulados": sintomas_finales
        }
    }

# Endpoint para consultar las evaluaciones anteriores de un paciente
@app.post("/api/historial/{id_usuario}")
def obtener_historial(id_usuario: int):
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Error de BD")
    try:
        cursor = conn.cursor(dictionary=True)
        # Buscamos los registros del usuario ordenados del más reciente al más antiguo
        cursor.execute(
            "SELECT nivel_riesgo, recomendacion, color_riesgo, fecha_evaluacion FROM evaluaciones WHERE id_usuario = %s ORDER BY fecha_evaluacion DESC",
            (id_usuario,)
        )
        registros = cursor.fetchall()

        historial = [
            {
                "nivel_riesgo": r["nivel_riesgo"],
                "recomendacion": r["recomendacion"],
                "color_riesgo": r["color_riesgo"],
                "fecha_evaluacion": str(r["fecha_evaluacion"])[:10]
            }
            for r in registros
        ]
        return {"status": "success", "data": historial}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()