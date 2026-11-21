from django.db import models
from django.db.models.signals import pre_save, pre_delete
from django.dispatch import receiver

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
    imagen = models.ImageField(upload_to='img_productos/', blank=True, null=True)
    def __str__(self):
        return f"{self.nombre} - ${self.precio_venta}"
    
class ZonaDomicilio(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, blank=True, default='')
    tarifa_base = models.DecimalField(max_digits=10, decimal_places=2, default=3000)
    descuento_compra_grande = models.DecimalField(max_digits=10, decimal_places=2, default=1500)
    monto_minimo_descuento = models.DecimalField(max_digits=12, decimal_places=2, default=90000)
    activa = models.BooleanField(default=True)

    def calcular_envio(self, subtotal):
        if subtotal >= self.monto_minimo_descuento:
            return max(0, self.tarifa_base - self.descuento_compra_grande)
        return self.tarifa_base

    def __str__(self):
        return f"{self.nombre} (${self.tarifa_base:,.0f})"


class Pedido(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('ENTREGADO', 'Entregado'),
        ('CANCELADO', 'Cancelado'),
    ]

    nombre_cliente = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30)
    tipo_entrega = models.CharField(max_length=20, default='domicilio')  # 'domicilio' o 'recoger'
    zona = models.ForeignKey(ZonaDomicilio, on_delete=models.SET_NULL, null=True, blank=True)
    direccion = models.CharField(max_length=255, blank=True, default='')
    metodo_pago = models.CharField(max_length=100, default='Efectivo')
    notas = models.TextField(blank=True, default='')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    costo_envio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pedido #{self.id} - {self.nombre_cliente} (${self.total:,.0f})"

    def save(self, *args, **kwargs):
        self.total = (self.subtotal or 0) + (self.costo_envio or 0)
        super().save(*args, **kwargs)

class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, related_name='detalles', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True)
    nombre_producto = models.CharField(max_length=200)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.cantidad}x {self.nombre_producto}"
    
@receiver(pre_save, sender=Pedido)
def devolver_stock_al_cancelar(sender, instance, **kwargs):
    if not instance.pk:
        return
    anterior = Pedido.objects.filter(pk=instance.pk).first()
    if anterior and anterior.estado != 'CANCELADO' and instance.estado == 'CANCELADO':
        for detalle in instance.detalles.all():
            if detalle.producto:
                detalle.producto.stock += detalle.cantidad
                detalle.producto.save()


@receiver(pre_delete, sender=Pedido)
def devolver_stock_al_eliminar(sender, instance, **kwargs):
    # Solo devuelve el stock si el pedido no estaba ya cancelado
    if instance.estado != 'CANCELADO':
        for detalle in instance.detalles.all():
            if detalle.producto:
                detalle.producto.stock += detalle.cantidad
                detalle.producto.save()