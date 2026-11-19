import os
import mysql.connector

# Función para abrir la conexión con nuestra base de datos MySQL
def get_db_connection():
    try:
        # Buscamos la ruta del archivo del certificado SSL (ca.pem) dentro de esta misma carpeta
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ca_path = os.path.join(base_dir, "ca.pem")

        # Leemos los datos de conexión desde las variables de entorno
        conn_params = {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 3306)),
            "user": os.environ.get("DB_USER", "root"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "database": os.environ.get("DB_NAME", "urotriaje_db"),
            "charset": "utf8mb4",
        }

        # Si no estamos en localhost y tenemos el certificado ca.pem, activamos el SSL para Aiven
        if conn_params["host"] != "localhost" and os.path.exists(ca_path):
            conn_params["ssl_ca"] = ca_path
            conn_params["ssl_verify_cert"] = True

        # Retornamos la conexión lista para ejecutar consultas
        return mysql.connector.connect(**conn_params)
    except Exception as e:
        print(f"Error conectando a MySQL: {e}")
        return None
