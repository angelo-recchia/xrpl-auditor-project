import psutil
import json
from datetime import datetime

def check_system_health():
    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    health_data = {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": cpu_usage,
        "memory": {
            "total": memory.total,
            "available": memory.available,
            "percent": memory.percent
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent
        }
    }
    
    with open("progress/system_health_status.json", "w") as f:
        json.dump(health_data, f, indent=4)
        
    print(f"=== INFORME DE SALUD DEL SISTEMA ===")
    print(f"CPU Uso: {cpu_usage}%")
    print(f"Memoria RAM Uso: {memory.percent}%")
    print(f"Disco Uso: {disk.percent}%")
    print(f"Reporte guardado en progress/system_health_status.json")

if __name__ == "__main__":
    check_system_health()
