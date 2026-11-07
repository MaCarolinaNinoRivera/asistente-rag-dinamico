# Base de Conocimiento: Gestión de Productos - Asistente Agro

## 1. ¿Qué es la pestaña de Productos?
Es el catálogo general de productos agrícolas del sistema. Aquí se muestran todos los productos independientes del lote donde se encuentren. Los productos que la Inteligencia Artificial detecta en las fotos de los inventarios se crean aquí de forma automática, pero también se pueden registrar de forma manual.

## 2. Creación Manual de Productos ("+ Nuevo producto")
Si no deseas crear un producto mediante el análisis automático de inventario, puedes hacerlo de forma manual haciendo clic en el botón **"+ Nuevo producto"**. Los campos disponibles son:
- **Nombre**: Nombre del producto agrícola.
- **Categoría**: Puede ser texto libre, o clasificado como "Agrícola / Cosecha", "Fruta", etc.
- **Unidad de medida**: Las opciones disponibles son unidad, kg (kilogramo), arroba, bulto o canastilla.
- **Peso de una unidad en kg (Opcional)**: Sirve para comparar tu precio local con el de la central de abastos, ya que en las centrales de abastos por lo general se paga por kilo.
- **Descripción**: Un campo de texto opcional para agregar detalles del producto.

## 3. Acciones sobre los Productos (Iconos en las tarjetas)
Cada tarjeta de producto cuenta con tres iconos de acción principales:

### A. Corregir producto (Icono de red/conexión 🔗)
Permite fusionar o corregir un producto mal registrado o detectado por error por la IA.
- **¿Para qué sirve?**: Si la IA registró "Ají" pero en realidad era "Arracacha", seleccionas esta opción para corregirlo y enviarlo al producto correcto.
- **Consecuencias de corregir un producto**:
  1. El stock del producto erróneo se suma al del producto correcto en cada lote.
  2. Todos los movimientos anteriores pasan al producto correcto y quedan marcados como corregidos.
  3. Los gastos y la receta pasan al producto correcto (si el producto de destino ya tiene una receta propia, se conserva la suya).
  4. Los análisis de tendencias del producto anterior se borran y se recalculan automáticamente para el nuevo lote.
  5. El producto erróneo (ej. Ají) desaparece por completo del catálogo.
  *Nota importante:* Esta acción no se puede deshacer.

### B. Actualizar / Editar producto (Icono de lápiz 📝)
Permite modificar los datos generales de un producto ya existente (como cambiar su nombre, categoría, unidad de medida, peso en kg o descripción).

### C. Eliminar producto (Icono de papelera 🗑️)
Permite borrar un producto del catálogo general de la finca.
