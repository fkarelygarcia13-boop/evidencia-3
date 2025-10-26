import datetime
import json
import os
import sqlite3
from sqlite3 import Error
from tabulate import tabulate

DB_FILE = "coworking.db"

def adapt_datetime(ts):
    return ts.isoformat(sep=' ')

def convert_datetime(s):
    return datetime.datetime.fromisoformat(s.decode())

sqlite3.register_adapter(datetime.datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

def ejecutar_consulta(query, parametros=(), fetch=False):
    conn = None
    try:
        with sqlite3.connect(DB_FILE,
                             detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, parametros)
            if fetch:
                return cursor.fetchall()
            conn.commit()
    except Error as e:
        print("Error en SQLite:", e)
    finally:
        if conn:
            conn.close()

def inicializar_bd():
    if not os.path.exists(DB_FILE):
        print("No se encontró base de datos, iniciando en blanco.")
    ejecutar_consulta("""
        CREATE TABLE IF NOT EXISTS clientes (
            id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellidos TEXT NOT NULL
        );
    """)
    ejecutar_consulta("""
        CREATE TABLE IF NOT EXISTS salas (
            id_sala INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cupo INTEGER NOT NULL CHECK (cupo > 0)
        );
    """)
    ejecutar_consulta("""
        CREATE TABLE IF NOT EXISTS reservaciones (
            folio INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER NOT NULL,
            id_sala INTEGER NOT NULL,
            fecha_registro TIMESTAMP NOT NULL,
            turno TEXT NOT NULL,
            evento TEXT NOT NULL,
            FOREIGN KEY(id_cliente) REFERENCES clientes(id_cliente),
            FOREIGN KEY(id_sala) REFERENCES salas(id_sala)
        );
    """)

def validar_evento(evento):
    return evento.strip() != ""

def validar_clave_cliente(clave, clientes):
    return any(c["id_cliente"] == clave for c in clientes)

def validar_texto(texto):
    return texto.replace(" ", "").isalpha()

def validar_fecha(fecha_str: str) -> datetime.date | None:
    """Valida fecha en formato mm-dd-aaaa, mínimo 2 días después de hoy y no domingo"""
    try:
        fecha = datetime.datetime.strptime(fecha_str, "%m-%d-%Y").date()
    except ValueError:
        print("Fecha con formato incorrecto, usa mm-dd-aaaa.")
        return None
    hoy = datetime.date.today()
    if (fecha - hoy).days < 2:
        print("Debe reservar con al menos 2 días de anticipación.")
        return None
    if fecha.weekday() == 6:
        sugerido = fecha + datetime.timedelta(days=1)
        print(f" No se pueden hacer reservaciones en domingo. Se sugiere: {sugerido.strftime('%m-%d-%Y')}")
        aceptar = input("¿Desea aceptar esta fecha propuesta? (s/n): ").lower()
        if aceptar == 's':
            fecha = sugerido
        else:
            return None
    return fecha

def sala_disponible(id_sala, fecha, turno):
    """Verifica que la sala esté libre en ese turno"""
    fecha_iso = fecha.strftime("%Y-%m-%d")  
    existente = ejecutar_consulta("""
        SELECT * FROM reservaciones
        WHERE id_sala=? AND DATE(fecha_registro)=? AND turno=?
    """, (id_sala, fecha_iso, turno), fetch=True)
    return len(existente) == 0

def registrar_cliente():
    nombre = input("Nombre del cliente: ").strip()
    if not validar_texto(nombre):
        print("Nombre inválido")
        return
    apellidos = input("Apellidos del cliente: ").strip()
    if not validar_texto(apellidos):
        print("Apellidos inválidos")
        return
    ejecutar_consulta("INSERT INTO clientes (nombre, apellidos) VALUES (?, ?)", (nombre, apellidos))
    print("Cliente registrado")

def registrar_sala():
    nombre = input("Nombre de la sala: ").strip()
    if not validar_texto(nombre):
        print("Nombre inválido")
        return
    try:
        cupo = int(input("Cupo de la sala: "))
        if cupo <= 0:
            raise ValueError
    except ValueError:
        print("Cupo inválido")
        return
    ejecutar_consulta("INSERT INTO salas (nombre, cupo) VALUES (?, ?)", (nombre, cupo))
    print("Sala registrada")

def validar_fecha_simple(fecha_str: str) -> datetime.date | None:
    """Valida formato mm-dd-aaaa, que sea fecha existente, al menos 2 días después y no domingo"""
    try:
        fecha = datetime.datetime.strptime(fecha_str, "%m-%d-%Y").date()
    except ValueError:
        print("Fecha no válida. Usa mm-dd-aaaa.")
        return None

    hoy = datetime.date.today()
    if (fecha - hoy).days < 2:
        print("Debe reservarse con al menos 2 días de anticipación.")
        return None

    if fecha.weekday() == 6:
        print("No se permiten reservas los domingos.")
        return None

    return fecha

def registrar_reservacion():
    clientes = ejecutar_consulta("SELECT * FROM clientes ORDER BY LOWER(apellidos), LOWER(nombre)", fetch=True)
    if not clientes:
        print("No hay clientes registrados")
        return

    print(tabulate([(c["id_cliente"], c["apellidos"], c["nombre"]) for c in clientes],
                   headers=["ID", "Apellidos", "Nombre"], tablefmt="grid"))

    while True:
        try:
            id_cliente = int(input("Clave del cliente: "))
        except ValueError:
            print("Clave inválida")
            continue
        if id_cliente == 0:
            return
        if validar_clave_cliente(id_cliente, clientes):
            break
        print("Cliente no encontrado, seleccione nuevamente o escriba '0' para cancelar")

    while True:
        fecha_str = input("Fecha de la reservación (mm-dd-aaaa): ").strip()
        fecha = validar_fecha_simple(fecha_str)
        if fecha:
            break

    salas = ejecutar_consulta("SELECT * FROM salas", fetch=True)
    if not salas:
        print("No hay salas registradas")
        return

    disponible_salas = []
    for s in salas:
        turnos_libres = []
        for turno in ["mañana", "tarde", "noche"]:
            if sala_disponible(s["id_sala"], fecha, turno):
                turnos_libres.append(turno)
        if turnos_libres:
            disponible_salas.append((s["id_sala"], s["nombre"], s["cupo"], turnos_libres))

    if not disponible_salas:
        print("No hay salas disponibles para esa fecha")
        return

    print(tabulate([(s[0], s[1], s[2], ", ".join(s[3])) for s in disponible_salas],
                   headers=["ID Sala", "Nombre", "Cupo", "Turnos disponibles"], tablefmt="grid"))

    while True:
        try:
            id_sala = int(input("Selecciona una sala: "))
            turno = input("Turno (mañana/tarde/noche): ").lower()
            if turno not in ["mañana", "tarde", "noche"]:
                raise ValueError
            if not sala_disponible(id_sala, fecha, turno):
                print("Sala ocupada en ese turno")
                continue
            break
        except ValueError:
            print("Selección inválida, intenta de nuevo")

    while True:
        evento = input("Nombre del evento: ").strip()
        if validar_evento(evento):
            break
        print("El nombre del evento no puede estar vacío ni ser solo espacios. Intenta de nuevo.")

    fecha_hora = datetime.datetime.combine(fecha, datetime.datetime.now().time())
    conn = None
    try:
        with sqlite3.connect(DB_FILE,
                             detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as conn:
            mi_cursor = conn.cursor()
            mi_cursor.execute("""
                INSERT INTO reservaciones (id_cliente, id_sala, fecha_registro, turno, evento)
                VALUES (?, ?, ?, ?, ?)
            """, (id_cliente, id_sala, fecha_hora, turno, evento))
            folio = mi_cursor.lastrowid

            cliente = ejecutar_consulta(
                "SELECT nombre || ' ' || apellidos AS nombre FROM clientes WHERE id_cliente=?",
                (id_cliente,), fetch=True)[0]["nombre"]
            sala = ejecutar_consulta(
                "SELECT nombre FROM salas WHERE id_sala=?",
                (id_sala,), fetch=True)[0]["nombre"]

            print(f"\n Reservación registrada correctamente!\n"
                  f"Folio: {folio}\n"
                  f"Cliente: {cliente}\n"
                  f"Sala: {sala}\n"
                  f"Fecha: {fecha.strftime('%m-%d-%Y')}\n"
                  f"Turno: {turno}\n"
                  f"Evento: {evento}\n")
    except sqlite3.Error as e:
        print("Error al registrar la reservación:", e)
    finally:
        if conn:
            conn.close()

def editar_evento():
    try:
        fi_str = input("Fecha inicial (mm-dd-aaaa): ")
        ff_str = input("Fecha final (mm-dd-aaaa): ")
        fi = datetime.datetime.strptime(fi_str, "%m-%d-%Y").date()
        ff = datetime.datetime.strptime(ff_str, "%m-%d-%Y").date()
    except ValueError:
        print("Fechas inválidas")
        return

    rango_fechas = [(fi + datetime.timedelta(days=i)) for i in range((ff - fi).days + 1)]
    reservaciones = []
    for f in rango_fechas:
        res = ejecutar_consulta("""
            SELECT folio, evento, fecha_registro FROM reservaciones
            WHERE DATE(fecha_registro) = ?
            ORDER BY fecha_registro
        """, (f.strftime("%Y-%m-%d"),), fetch=True)
        reservaciones.extend(res)

    if not reservaciones:
        print("No hay reservaciones en ese rango")
        return

    def mostrar_tabla():
        print(tabulate(
            [(r["folio"], r["evento"], r["fecha_registro"].strftime("%m-%d-%Y")) for r in reservaciones],
            headers=["Folio", "Evento", "Fecha"],
            tablefmt="grid"
        ))

    while True:
        mostrar_tabla()
        print("Ingrese el folio del evento a editar o '0' para cancelar")
        try:
            folio = int(input("Folio: "))
        except ValueError:
            print("Folio inválido")
            continue

        if folio == 0:
            print("Operación cancelada")
            return

        if any(r["folio"] == folio for r in reservaciones):
            break
        print("Folio no encontrado en el rango seleccionado, intente de nuevo")

    while True:
        nuevo_evento = input("Nuevo nombre del evento: ").strip()
        if nuevo_evento:
            break
        print("El nombre del evento no puede estar vacío")

    ejecutar_consulta("UPDATE reservaciones SET evento=? WHERE folio=?", (nuevo_evento, folio))
    print("Evento actualizado correctamente")


def consultar_reservaciones():
    fecha_str = input("Fecha a consultar (mm-dd-aaaa, vacío para hoy): ").strip()
    if not fecha_str:
        fecha = datetime.date.today()
    else:
        try:
            fecha = datetime.datetime.strptime(fecha_str, "%m-%d-%Y").date()
        except ValueError:
            print("Fecha inválida")
            return
    fecha_iso = fecha.strftime("%Y-%m-%d")
    registros = ejecutar_consulta("""
        SELECT r.folio, c.nombre || ' ' || c.apellidos AS cliente,
               s.nombre AS sala, r.turno, r.evento
        FROM reservaciones r
        JOIN clientes c ON r.id_cliente = c.id_cliente
        JOIN salas s ON r.id_sala = s.id_sala
        WHERE DATE(r.fecha_registro) = ?
        ORDER BY r.turno
    """, (fecha_iso,), fetch=True)
    if not registros:
        print("No hay reservaciones para esa fecha")
        return
    print(tabulate([(r["folio"], r["cliente"], r["sala"], r["turno"], r["evento"]) for r in registros],
                   headers=["Folio", "Cliente", "Sala", "Turno", "Evento"], tablefmt="grid"))
    opcion = input("¿Deseas exportar a JSON? (s/n): ").lower()
    if opcion == "s":
        datos = [dict(r) for r in registros]
        with open(f"reporte_{fecha.strftime('%m-%d-%Y')}.json", "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)
        print(f"Exportado como reporte_{fecha.strftime('%m-%d-%Y')}.json")

def menu():
    inicializar_bd()
    while True:
        print("""
========= MENÚ PRINCIPAL =========
1. Registrar cliente
2. Registrar sala
3. Registrar reservación
4. Editar nombre de evento
5. Consultar reservaciones
6. Salir
""")
        opcion = input("Selecciona una opción: ")
        if opcion == "1":
            registrar_cliente()
        elif opcion == "2":
            registrar_sala()
        elif opcion == "3":
            registrar_reservacion()
        elif opcion == "4":
            editar_evento()
        elif opcion == "5":
            consultar_reservaciones()
        elif opcion == "6":
            confirmar = input("¿Seguro que deseas salir? (s/n): ").lower()
            if confirmar == "s":
                print("Saliendo del sistema.")
                break
        else:
            print("Opción inválida")

if __name__ == "__main__":
    menu()