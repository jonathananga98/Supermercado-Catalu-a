// ========================================================
// CONEXIÓN CON API REST (DJANGO REST FRAMEWORK)
// ========================================================

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

document.addEventListener("DOMContentLoaded", function () {
    const csrftoken = getCookie('csrftoken');
    const badgeCarrito = document.getElementById('contador-carrito');
    const toastEl = document.getElementById('toastCarrito');
    const toastTexto = document.getElementById('toastCarritoTexto');
    const toastBootstrap = toastEl ? new bootstrap.Toast(toastEl, { delay: 2500 }) : null;

    // 1. Agregar producto al carrito vía POST sin recargar la página
    function agregarProductoViaAPI(productoId, botonElement = null) {
        const urlApi = `/api/carrito/agregar/${productoId}/`;
        let textoOriginal = '';

        if (botonElement) {
            textoOriginal = botonElement.innerHTML;
            botonElement.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Agregando...';
            botonElement.style.pointerEvents = 'none';
        }

        fetch(urlApi, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json().then(data => ({ okHttp: response.ok, body: data })))
        .then(({ okHttp, body }) => {
            if (okHttp && body.ok) {
                if (badgeCarrito) badgeCarrito.textContent = body.cart_count;
                if (toastEl && toastBootstrap) {
                    toastEl.classList.remove('bg-warning', 'text-dark');
                    toastEl.classList.add('bg-success', 'text-white');
                    toastTexto.innerHTML = `<i class="bi bi-check-circle-fill me-2"></i> ${body.mensaje}`;
                    toastBootstrap.show();
                }
            } else if (toastEl && toastBootstrap) {
                toastEl.classList.remove('bg-success', 'text-white');
                toastEl.classList.add('bg-warning', 'text-dark');
                toastTexto.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-2"></i> ${body.mensaje || 'No se pudo agregar'}`;
                toastBootstrap.show();
            }
        })
        .catch(err => console.error('Error conectando con API DRF:', err))
        .finally(() => {
            if (botonElement) {
                botonElement.innerHTML = textoOriginal;
                botonElement.style.pointerEvents = 'auto';
            }
        });
    }

    // Interceptar clics en los botones "Agregar" de las tarjetas
    document.querySelectorAll('.btn-agregar-carrito').forEach(boton => {
        boton.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            const match = href ? href.match(/\/(\d+)\/?$/) : null;
            if (match) {
                e.preventDefault();
                agregarProductoViaAPI(match[1], this);
            }
        });
    });

    // 2. Buscador en tiempo real consumiendo GET /api/productos/?q=...
    const inputBusqueda = document.getElementById('input-busqueda-api');
    const cajaResultados = document.getElementById('resultados-busqueda-api');
    let timerBusqueda = null;

    if (inputBusqueda && cajaResultados) {
        inputBusqueda.addEventListener('input', function () {
            clearTimeout(timerBusqueda);
            const texto = this.value.trim();

            if (texto.length < 2) {
                cajaResultados.classList.add('d-none');
                cajaResultados.innerHTML = '';
                return;
            }

            timerBusqueda = setTimeout(() => {
                fetch(`/api/productos/?q=${encodeURIComponent(texto)}`)
                    .then(res => res.json())
                    .then(data => {
                        if (!data.resultados || data.resultados.length === 0) {
                            cajaResultados.innerHTML = `
                                <div class="list-group-item text-muted small py-3 text-center">
                                    No se encontraron productos para "${texto}"
                                </div>`;
                            cajaResultados.classList.remove('d-none');
                            return;
                        }

                        cajaResultados.innerHTML = data.resultados.map(prod => `
                            <div class="list-group-item list-group-item-action d-flex align-items-center justify-content-between py-2 px-3">
                                <div class="d-flex align-items-center gap-2 overflow-hidden">
                                    <img src="${prod.imagen_url || '/static/logo.png'}"
                                         alt="${prod.nombre}"
                                         style="width: 40px; height: 40px; object-fit: contain; background: #fff; border-radius: 8px; padding: 2px;">
                                    <div class="text-truncate">
                                        <div class="fw-bold text-dark small text-truncate">${prod.nombre}</div>
                                        <div class="text-success fw-bold small">$${prod.precio_venta}
                                            <span class="text-muted fw-normal ms-1">(Stock: ${prod.stock})</span>
                                        </div>
                                    </div>
                                </div>
                                <button type="button"
                                        class="btn btn-sm btn-success rounded-pill px-3 ms-2 flex-shrink-0 btn-quick-add"
                                        data-id="${prod.id}"
                                        ${prod.stock <= 0 ? 'disabled' : ''}>
                                    + Agregar
                                </button>
                            </div>
                        `).join('');

                        cajaResultados.classList.remove('d-none');

                        cajaResultados.querySelectorAll('.btn-quick-add').forEach(btn => {
                            btn.addEventListener('click', function (ev) {
                                ev.stopPropagation();
                                agregarProductoViaAPI(this.dataset.id, this);
                            });
                        });
                    })
                    .catch(err => console.error('Error en búsqueda API:', err));
            }, 250);
        });

        // Cerrar lista desplegable al hacer clic fuera
        document.addEventListener('click', function (e) {
            if (!inputBusqueda.contains(e.target) && !cajaResultados.contains(e.target)) {
                cajaResultados.classList.add('d-none');
            }
        });
    }

    // 3. Actualizar cantidades (sumar, restar, eliminar) en carrito.html vía POST
    document.querySelectorAll('.btn-accion-carrito').forEach(btn => {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            const productoId = this.dataset.id;
            const accion = this.dataset.accion;

            fetch(`/api/carrito/actualizar/${productoId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ accion: accion })
            })
            .then(res => res.json().then(data => ({ okHttp: res.ok, body: data })))
            .then(({ okHttp, body }) => {
                if (!okHttp || !body.ok) {
                    if (toastEl && toastBootstrap) {
                        toastEl.classList.remove('bg-success', 'text-white');
                        toastEl.classList.add('bg-warning', 'text-dark');
                        toastTexto.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-2"></i> ${body.mensaje || 'No se pudo actualizar'}`;
                        toastBootstrap.show();
                    }
                    return;
                }

                // Si quedó en 0 o se eliminó, quitar la fila de la tabla
                if (body.cantidad <= 0) {
                    const fila = btn.closest('tr');
                    if (fila) fila.remove();
                    if (body.cart_count === 0) {
                        window.location.reload(); // Muestra la vista limpia de "Tu carrito está vacío"
                        return;
                    }
                } else {
                    const spanCant = document.getElementById(`cantidad-${productoId}`);
                    const tdSubtotal = document.getElementById(`subtotal-${productoId}`);
                    if (spanCant) spanCant.textContent = body.cantidad;
                    if (tdSubtotal) tdSubtotal.textContent = `$${body.subtotal_item}`;
                }

                // Actualizar Subtotal y Total del resumen lateral
                const resSub = document.getElementById('resumen-subtotal');
                const resTot = document.getElementById('resumen-total');
                if (resSub) resSub.textContent = `$${body.total_general}`;
                if (resTot) resTot.textContent = `$${body.total_general}`;
            })
            .catch(err => console.error('Error actualizando carrito API:', err));
        });
    });
});