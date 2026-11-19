def evaluar_sintomas(s_disuria: bool, s_hematuria: bool, s_fiebre: bool, s_polaquiuria: bool, s_dolor_lumbar: bool) -> dict:
    """
    Aqui evaluamos los sintomas del paciente para determinar su riesgo.
    Separamos los problemas urinarios de los malestares generales.
    """
    
    # Primero descartamos si el paciente no tiene ningun sintoma urinario
    if not (s_disuria or s_hematuria or s_polaquiuria):
        
        # Si hay fiebre o dolor lumbar pero sin molestias al orinar, sugerimos medicina general
        if s_fiebre or s_dolor_lumbar:
            sintomas_presentes = []
            if s_fiebre: sintomas_presentes.append("fiebre")
            if s_dolor_lumbar: sintomas_presentes.append("dolor lumbar")
            texto_sintomas = " y ".join(sintomas_presentes)
            
            return {
                "nivel_riesgo": "Riesgo No Urinario",
                "recomendacion": f"Presentas {texto_sintomas}, pero sin molestias al orinar. Podría tratarse de un cuadro muscular, viral o general. Te sugiero consultar por medicina general.",
                "color_riesgo": "#9E9E9E" 
            }
            
        # Si no detectamos ningun malestar, devolvemos un perfil sin riesgo
        else:
            return {
                "nivel_riesgo": "Sin Riesgo Urológico",
                "recomendacion": "No se detectan patrones de alarma en tus vías urinarias. Si tus molestias (como dolor de cabeza o malestar) persisten, te recomiendo agendar una cita con medicina general y mantenerte bien hidratado.",
                "color_riesgo": "#388E3C" 
            }

    # A partir de este punto, analizamos los casos que si tienen sintomas urinarios activos

    # Si tiene fiebre junto con otros malestares, lo tomamos como riesgo alto y recomendamos urgencias
    if s_fiebre and (s_dolor_lumbar or s_disuria or s_hematuria):
        return {
            "nivel_riesgo": "Riesgo Alto",
            "recomendacion": "Alerta: Posible infección sistémica (ej. pielonefritis). Debe acudir a un servicio de URGENCIAS lo antes posible.",
            "color_riesgo": "#D32F2F" 
        }
        
    # Si hay sangre en la orina y dolor, le indicamos atencion prioritaria
    if s_hematuria and (s_disuria or s_dolor_lumbar):
        return {
            "nivel_riesgo": "Riesgo Medio Alto",
            "recomendacion": "Presencia de sangre y dolor. Requiere evaluación médica prioritaria. Acuda a consulta sin demoras.",
            "color_riesgo": "#E64A19" 
        }

    # Un cuadro muy comun de infeccion: le duele al orinar y va muchas veces al baño
    if s_disuria and s_polaquiuria:
        return {
            "nivel_riesgo": "Riesgo Medio",
            "recomendacion": "Posible infección del tracto urinario localizada. Se recomienda programar una CONSULTA EXTERNA prioritaria con su médico.",
            "color_riesgo": "#F57C00" 
        }

    # Si solo presenta un sintoma aislado, el riesgo es de leve a medio
    if s_disuria or s_polaquiuria or s_hematuria:
        return {
            "nivel_riesgo": "Riesgo Leve a Medio",
            "recomendacion": "Presentas un síntoma urinario de atención. Mantén buena hidratación y agenda una revisión médica en los próximos días si la molestia no desaparece.",
            "color_riesgo": "#FBC02D" 
        }