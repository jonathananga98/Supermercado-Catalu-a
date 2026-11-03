import os
import django
import pandas as pd

# Configuramos el entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'primer_proyecto.settings')
django.setup()

from primer_app.models import Categoria, Producto

def run():
    archivo_excel = 'Productos_1.xlsx'
    if not os.path.exists(archivo_excel):
        print(f"Error: No se encontró el archivo '{archivo_excel}' en la carpeta raíz del proyecto.")
        return

    print("Leyendo archivo Excel...")
    df = pd.read_excel(archivo_excel)

    def limpiar_precio(val):
        if pd.isna(val) or val == '$0' or val == 0:
            return 0.0
        if isinstance(val, str):
            val = val.replace('$', '').replace(',', '').strip()
            try:
                return float(val)
            except ValueError:
                return 0.0
        return float(val)

    def limpiar_entero(val):
        if pd.isna(val) or val == '-' or val == '':
            return 0
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    contador = 0
    for index, row in df.iterrows():
        codigo = str(row['Código']).strip() if pd.notna(row['Código']) else f"SIN_COD_{index}"
        nombre_prod = str(row['Producto']).strip()
        p_costo = limpiar_precio(row['P. Costo'])
        p_venta = limpiar_precio(row['P. Venta'])
        p_mayoreo = limpiar_precio(row['P. Mayoreo'])
        nombre_depto = str(row['Departamento']).strip() if pd.notna(row['Departamento']) else 'General'
        
        existencia = limpiar_entero(row['Existencia'])
        inv_min = limpiar_entero(row['Inv. Mínimo'])
        inv_max = limpiar_entero(row['Inv. Máximo'])
        tipo_venta = str(row['Tipo de Venta']).strip() if pd.notna(row['Tipo de Venta']) else 'UNIDAD'

        # Gestionar Categoría / Departamento
        categoria, _ = Categoria.objects.get_or_create(nombre=nombre_depto)

        # Crear o actualizar el producto
        Producto.objects.update_or_create(
            codigo=codigo,
            defaults={
                'nombre': nombre_prod,
                'precio_costo': p_costo,
                'precio_venta': p_venta,
                'precio_mayoreo': p_mayoreo,
                'categoria': categoria,
                'stock': existencia,
                'inv_minimo': inv_min if inv_min > 0 else 1,
                'inv_maximo': inv_max,
                'tipo_venta': tipo_venta
            }
        )
        contador += 1

    print(f"¡Importación exitosa! Se procesaron y cargaron {contador} productos correctamente.")

if __name__ == '__main__':
    run()