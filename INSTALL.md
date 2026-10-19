# Instalación de speckit-skills

Guía para instalar el plugin, comprobar que funciona y resolver los problemas habituales.

Hay dos caminos:

- **A. Local**: para probarlo hoy, sin GitHub.
- **B. GitHub**: la instalación definitiva, la misma en todas tus máquinas.

Lo recomendable es empezar por A y pasar a B cuando lo hayas probado en un proyecto real.

---

## 0. Requisitos

```sh
claude --version     # probado con 2.1.303; si es más antigua: claude update
python3 --version    # 3.9 o superior
specify version      # Spec Kit con la integración claude
```

Para que el plugin tenga algo que asociar, necesitas skills de dominio instaladas (FastAPI, Alfresco, tests, etc.) en alguna de estas rutas:

- `.claude/skills/` del proyecto
- `~/.claude/skills/`
- las skills de plugins (`~/.claude/plugins/**/skills`)
- `.github/skills/` o `.agents/skills/`

---

## A. Instalación local (sin GitHub)

1. Descomprime el zip en una carpeta que no vayas a mover:

   ```sh
   mkdir -p ~/tools && cd ~/tools && unzip ~/Downloads/speckit-skills.zip
   ```

   Claude Code registra esa ruta. Si mueves la carpeta, el plugin deja de cargar.

2. Registra la carpeta como marketplace e instala el plugin a nivel de usuario:

   ```sh
   claude plugin marketplace add ~/tools/speckit-skills
   claude plugin install speckit-skills@horelvis-speckit --scope user
   ```

3. Comprueba que ha quedado instalado:

   ```sh
   claude plugin list
   ```

   `speckit-skills` debe aparecer habilitado. Dentro de Claude Code, `/hooks` debe mostrar `UserPromptExpansion` y `PreToolUse` (matcher `Skill`) asociados al plugin.

---

## B. Instalación desde GitHub

1. Crea el repo y súbelo:

   ```sh
   cd ~/tools/speckit-skills
   git init && git add . && git commit -m "speckit-skills 0.1.0"
   gh repo create horelvis/speckit-skills --public --source . --push
   ```

   También puede ser privado (`--private`), siempre que tu git tenga acceso al repo.

2. Si antes hiciste la instalación local, quítala:

   ```sh
   claude plugin uninstall speckit-skills@horelvis-speckit
   claude plugin marketplace remove horelvis-speckit
   ```

3. Instala desde GitHub. Es lo único que hay que hacer en cada máquina:

   ```sh
   claude plugin marketplace add horelvis/speckit-skills
   claude plugin install speckit-skills@horelvis-speckit --scope user
   ```

4. Para publicar nuevas versiones:

   - sube `version` en `plugins/speckit-skills/.claude-plugin/plugin.json`;
   - haz commit y push;
   - en cada máquina: `claude plugin marketplace update horelvis-speckit`.

---

## C. Limpieza del preset anterior

Si instalaste el preset `skill-waves` en algún proyecto, quítalo para que las instrucciones no se dupliquen:

```sh
specify preset list
specify preset remove skill-waves
```

---

## D. Primera prueba

1. Abre `claude` en un proyecto con `.specify/` y pídele:

   ```
   Ejecuta el discover de speckit-skills y dime qué skills ves para este proyecto.
   ```

   Si la lista sale vacía, no sigas: primero instala o crea skills de dominio.

2. Haz una feature pequeña, de 10 a 20 tareas, con el flujo de siempre: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks`.

   Revisa tres cosas:

   - `plan.md` tiene una sección **Skills Map** con una skill por área, o `none` donde no aplica ninguna.
   - Cada tarea de `tasks.md` lleva `(skill: …)` y `(depends on …)`.
   - Al final de `tasks.md` hay una sección **Execution Waves**.

3. Lanza `/speckit-implement`. Debe mostrar la oleada actual y lanzar varios subagentes a la vez, uno por skill. Cada uno empieza leyendo su `SKILL.md`.

4. Revisa el resultado de `plan`:

   - Si casi todos los grupos tienen una sola tarea (`single_task_groups`), el modelo marca más dependencias de las necesarias.
   - Si aparecen muchos `(skill: none)` donde había una skill que encajaba, el problema está en el Skills Map. Revisa las descripciones de esas skills.

---

## Desactivar

| Alcance | Cómo |
|---|---|
| Un proyecto | crear `.specify/speckit-skills.off` |
| Una sesión | `SPECKIT_SKILLS_DISABLE=1 claude` |
| Del todo | `claude plugin disable speckit-skills` |

---

## Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| Los comandos de Spec Kit no reciben las instrucciones del plugin | No estás dentro del proyecto, falta `.specify/`, o existe `.specify/speckit-skills.off` | Abre `claude` en la raíz del proyecto o en una subcarpeta |
| `/hooks` no muestra `UserPromptExpansion` | Claude Code antiguo | `claude update` |
| `skill 'x' is not installed` | La skill está en una ruta que el plugin no revisa | `export SKILL_WAVES_DIRS=/ruta/a/skills` |
| El plugin no carga tras mover la carpeta | La instalación local depende de la ruta | Vuelve a hacer el paso A.2 o pasa a la instalación desde GitHub |
| `/speckit-implement` avisa de un `tasks.md` sin anotaciones | El `tasks.md` es anterior al plugin | Vuelve a ejecutar `/speckit-tasks` |
| Dos subagentes tocan el mismo fichero | Una tarea modifica ficheros que no menciona en su descripción | Añade la ruta a la descripción de la tarea y regenera con `plan --write` |

---

## Compatibilidad con spec-kit-schedule

El `tasks.md` que genera este plugin se puede usar también con [spec-kit-schedule](https://github.com/jfranc38/spec-kit-schedule). En un proyecto donde compense su solver, instala la extensión en ese proyecto y usa `/speckit-schedule-implement` sobre las mismas tareas, sin regenerarlas.

Para que Schedule acepte los nombres de tus skills, deben ir en minúsculas y con guiones (`[a-z][a-z0-9_-]*`). Si no lo están, el plugin avisa.
