import os
import shutil
import re
import unicodedata
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'primer_proyecto.settings')
django.setup()

from primer_app.models import Producto

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_LOTE = os.path.join(BASE_DIR, 'media', 'Descargas_lote')
CARPETA_MEDIA = os.path.join(BASE_DIR, 'media', 'img_productos')

def limpiar_texto(texto):
    """ Convierte texto a minúsculas, reemplaza guiones por espacios y quita tildes """
    texto = texto.replace('_', ' ').replace('-', ' ')
    texto = unicodedata.normalize('NFD', texto)
    texto = re.sub(r'[\u0300-\u036f]', '', texto)
    texto = re.sub(r'[^a-zA-Z0-9\s]', '', texto)
    return texto.lower().strip()

def procesar_lote():
    print(f"🔍 Buscando archivos en: {CARPETA_LOTE}")
    
    if not os.path.exists(CARPETA_LOTE):
        print(f"⚠️ La carpeta no existe en esa ruta.")
        return

    archivos = os.listdir(CARPETA_LOTE)
    print(f"📂 Archivos encontrados ({len(archivos)}): {archivos}")

    if not archivos:
        print("📁 La carpeta está vacía.")
        return

    productos = list(Producto.objects.all())
    exitos = 0

    
    EXTENSIONES_VALIDAS = ['.jpg', '.jpeg', '.png', '.webp', '.jfif']

    for archivo in archivos:
        nombre_sin_ext, ext = os.path.splitext(archivo)
        if ext.lower() not in EXTENSIONES_VALIDAS:
            continue

        nombre_limpio = limpiar_texto(nombre_sin_ext)
        palabras_clave = [p for p in nombre_limpio.split() if len(p) > 1]

        producto_encontrado = None

        # 1. Coincidencia si todas las palabras clave del archivo están en el nombre del producto
        for prod in productos:
            nombre_prod_limpio = limpiar_texto(prod.nombre)
            if palabras_clave and all(palabra in nombre_prod_limpio for palabra in palabras_clave):
                producto_encontrado = prod
                break

        # 2. Búsqueda por palabra clave principal si no hubo coincidencia completa
        if not producto_encontrado and palabras_clave:
            palabra_principal = palabras_clave[0]
            if len(palabra_principal) > 3:
                for prod in productos:
                    if palabra_principal in limpiar_texto(prod.nombre):
                        producto_encontrado = prod
                        break

        if producto_encontrado:
            ruta_origen = os.path.join(CARPETA_LOTE, archivo)
            ruta_destino = os.path.join(CARPETA_MEDIA, archivo)
            
            shutil.move(ruta_origen, ruta_destino)
            producto_encontrado.imagen = f'img_productos/{archivo}'
            producto_encontrado.save()
            
            exitos += 1
            print(f"✅ Vinculado: '{archivo}' ---> [{producto_encontrado.nombre}]")
        else:
            print(f"❌ Sin coincidencia para: '{archivo}' (buscado como: '{nombre_limpio}')")

    print(f"\n🚀 Proceso terminado. Se vincularon {exitos} imágenes.")

if __name__ == '__main__':
    procesar_lote()