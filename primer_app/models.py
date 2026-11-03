from django.db import models

# Modelo para las categorías de los productos (Ej: Lácteos, Abarrotes, Limpieza)
class Categoria(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre

# Modelo para los productos del supermercado
class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True, null=True, blank=True)
    nombre = models.CharField(max_length=200)
    precio_costo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_mayoreo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Departamento")
    stock = models.IntegerField(default=0, verbose_name="Existencia")
    inv_minimo = models.IntegerField(default=1)
    inv_maximo = models.IntegerField(default=0)
    tipo_venta = models.CharField(max_length=50, default='UNIDAD')

    def __str__(self):
        return f"{self.nombre} - ${self.precio_venta}"