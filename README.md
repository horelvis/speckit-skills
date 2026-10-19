# speckit-skills

Plugin de Claude Code para [GitHub Spec Kit](https://github.com/github/spec-kit). Asocia cada tarea a una de tus skills y ejecuta `/speckit-implement` por oleadas: cada grupo de tareas que comparte skill va a un subagente que lee el `SKILL.md` antes de empezar.

Se instala una vez a nivel de usuario y funciona en todos los proyectos que tengan `.specify/`. No hay nada que instalar por proyecto.

## Por qué

`/speckit-tasks` genera tareas atómicas y `/speckit-implement` confía en que las skills se activen solas. Eso depende de que la descripción de la skill coincida con lo que se pide, y una tarea como "crear modelo User en src/models/user.py" casi nunca coincide. El resultado es que se implementa sin las skills que tienes instaladas.

## Qué hace

| Comando | Añade |
|---|---|
| `/speckit-plan` | Sección **Skills Map** en `plan.md`: qué skill cubre cada área de la feature, eligiendo solo entre las instaladas |
| `/speckit-tasks` | `(skill: x)` y `(depends on T…)` en cada tarea, validación, y sección **Execution Waves** en `tasks.md` |
| `/speckit-implement` | Bucle `next` → subagentes en paralelo, uno por skill → `mark`, oleada a oleada |

El plugin no modifica Spec Kit. Usa dos hooks que añaden instrucciones a los comandos originales:

- `UserPromptExpansion`: cuando escribes el comando.
- `PreToolUse` con matcher `Skill`: cuando lo invoca el modelo, por ejemplo en un handoff.

Fuera de un proyecto Spec Kit no hace nada.

## Modelo de ejecución

- **Fases** (`##` en tasks.md): son barreras. Se mantiene el orden por historia de usuario y el MVP incremental.
- **Oleadas**, dentro de cada fase: `oleada(t) = 1 + max(oleada(dependencias))`.
- **Grupos**, dentro de cada oleada: tareas con la misma skill. Los grupos de una oleada no comparten ficheros y van en paralelo.
- **Ficheros compartidos**: si dos grupos tocan el mismo fichero en la misma oleada, la tarea posterior pasa a la oleada siguiente, junto con las que dependen de ella.
- **Estado**: solo las casillas de `tasks.md`, que escribe el orquestador con `mark`. Se puede reanudar en cualquier momento.

Todo esto lo calcula `scripts/skill_waves.py` (solo librería estándar) de forma determinista. El LLM solo anota las tareas y lanza los subagentes.

## Compatible con spec-kit-schedule

Las anotaciones usan la sintaxis de [spec-kit-schedule](https://github.com/jfranc38/spec-kit-schedule), así que el mismo `tasks.md` funciona con los dos. Si en un proyecto grande quieres su solver (CP-SAT, camino crítico), instalas Schedule y usas `/speckit-schedule-implement` sobre las mismas tareas. Está comprobado con su parser: lee skills y dependencias sin avisos.

```text
- [ ] T005 [US1] POST /users in src/api/users.py (skill: fastapi-endpoints) (depends on T003, T004)
- [ ] T001 Create project structure (skill: none) (depends on none)
```

Para que también sea compatible con Schedule, nombra tus skills en minúsculas con guiones (`[a-z][a-z0-9_-]*`). Si no, el plugin avisa.

## Instalación

Desde GitHub, una vez:

```sh
claude plugin marketplace add horelvis/speckit-skills
claude plugin install speckit-skills@horelvis-speckit --scope user
```

O dentro de Claude Code:

```
/plugin marketplace add horelvis/speckit-skills
/plugin install speckit-skills@horelvis-speckit
```

Requisitos: Claude Code con soporte de `UserPromptExpansion` (probado con 2.1.303), `python3` >= 3.9 y Spec Kit con la integración `claude`.

## Desactivar

- Para un proyecto: crea `.specify/speckit-skills.off`.
- Para una sesión: `SPECKIT_SKILLS_DISABLE=1`.
- Del todo: `claude plugin disable speckit-skills`.

## Script

```sh
S=~/.claude/plugins/.../speckit-skills/scripts/skill_waves.py   # la ruta exacta aparece en las instrucciones inyectadas
python3 $S discover                          # skills visibles para el proyecto
python3 $S plan specs/001-x/tasks.md --markdown --write
python3 $S next specs/001-x/tasks.md         # oleada actual + briefs
python3 $S mark specs/001-x/tasks.md T003 T004
python3 $S mark specs/001-x/tasks.md --report reply.txt
```

`discover` busca en `.claude/skills`, `.github/skills`, `.agents/skills`, `~/.claude/skills`, `~/.agents/skills` y en las skills de plugins (`~/.claude/plugins/**/skills`). Para añadir rutas, usa `SKILL_WAVES_DIRS`. Ignora las `speckit-*`.

## Tests

```sh
python3 -m unittest tests/test_skill_waves.py
```

## Limitaciones

- El agrupamiento solo es tan bueno como las dependencias. Si son demasiado prudentes, cada grupo acaba con una sola tarea. `plan` lo muestra en `single_task_groups`.
- La detección de conflictos solo ve los ficheros que aparecen en la descripción de la tarea.
- Con un `tasks.md` antiguo, sin anotaciones, todo se ejecuta como `skill: none`. `/speckit-implement` avisa y propone regenerar las tareas.
- Sin subagentes, los grupos se ejecutan en secuencia, pero la carga del `SKILL.md` sigue siendo explícita.
