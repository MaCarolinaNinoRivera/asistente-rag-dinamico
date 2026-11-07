# Base de Conocimiento: Gestión de Productos - Asistente Agro

## 1. ¿Qué es la pestaña de Productos?
Es el catálogo general de productos agrícolas del sistema. Muestra todos los productos registrados de forma independiente del lote en el que se encuentren. Los productos que la Inteligencia Artificial detecta en las fotos de los inventarios se crean aquí automáticamente, pero también se pueden registrar y gestionar de forma manual.

## 2. Creación Manual de Productos ("+ Nuevo producto")
Si no deseas crear un producto mediante el análisis automático de inventario, puedes hacerlo haciendo clic en el botón superior **"+ Nuevo producto"**. Los campos que solicita son:
- **Nombre**: Nombre del producto agrícola.
- **Categoría**: Clasificación libre o seleccionada (ej. Agrícola / Cosecha, Fruta, etc.).
- **Unidad de medida**: Opciones disponibles como unidad, kg (kilogramo), arroba, bulto o canastilla.
- **Peso de una unidad en kg (Opcional)**: Sirve para comparar tu precio local con el de la central de abastos, ya que allí generalmente se paga por kilo.
- **Descripción**: Un campo de texto opcional para agregar detalles.

## 3. Acciones sobre las Tarjetas de Productos
Cada tarjeta de producto cuenta con tres iconos principales en la parte superior derecha y un enlace especial en la parte inferior:

### A. Corregir producto (Icono de red o nodos 🔗)
Permite fusionar un producto mal registrado por error de la IA hacia el producto correcto.
- **¿Qué pasa al corregir?**: Si la IA registró "Ají" pero era "Arracacha", seleccionas el producto real. El stock de Ají se suma al de Arracacha en cada lote, los movimientos y gastos se transfieren (quedando marcados como corregidos), las recetas se heredan, los análisis de tendencias se recalculan y el Ají desaparece del catálogo para siempre. Esta acción no se puede deshacer.

### B. Actualizar producto (Icono de edición con casilla y raya 📝)
Permite modificar los datos generales del producto (nombre, categoría, unidad de medida, peso o descripción).

### C. Eliminar producto (Icono de papelera roja 🗑️)
Permite borrar definitivamente el producto del catálogo general de la finca.

## 4. Receta y qué comprar para sembrar (Enlace inferior)
Al hacer clic en **"Receta y qué comprar para sembrar"**, se abre una ventana emergente ("Receta del cultivo") para configurar las necesidades del cultivo y calcular costos de producción:
- **¿Cómo cuentas lo que siembras?**: Puedes elegir entre *Por planta*, *Por metro cuadrado*, *Por surco* o *Por hectárea*.
- **Rendimiento y tiempo**: Define cuánto produce cada planta (en unidad) y cuántos días tarda en dar cosecha.
- **¿Qué necesita cada planta?**: Permite asociar los insumos necesarios para el cultivo seleccionándolos del inventario. 
- **Importante sobre los insumos**: La información de los insumos se alimenta directamente de lo que guardaste previamente en tu inventario de insumos. **Si no aparece ningún insumo en la lista desplegable, debes crearlos primero** en el módulo correspondiente antes de poder asignarlos a la receta.
