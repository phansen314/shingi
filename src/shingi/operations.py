"""Operations: the domain layer (see operations.md).

Each operation takes its input and the --config file, and returns its result and its warnings.
"""

import errno
import heapq
import json
import os
import posixpath
import uuid
from importlib.metadata import version as package_version

from shingi import hooks, inputs, koan, rules as rules_file, units
from shingi.envelope import OperationError


def version(inp, config):
    inputs.check("version", inp)
    return {"version": package_version("shingi")}, []


def kinds(inp, config):
    inputs.check("kinds", inp)
    rules = rules_file.load(config)
    return {
        "kinds": [
            {"name": name, "description": kind.get("description", ""), "suggests": kind.get("suggests", [])}
            for name, kind in sorted(rules.kinds.items(), key=lambda item: item[0].encode())
        ]
    }, []


def where(inp, config):
    inputs.check("where", inp)
    rules = rules_file.load(config)
    return units.read_unit(rules, named_unit(rules, inp))


def named_unit(rules, inp):
    """The path of the unit `where` and `context` report: `unit`, or the one `cwd` is in."""
    if "cwd" in inp:
        return units.resolve_directory(rules, inp["cwd"])
    path = inp["unit"]
    units.check_path(path, "/unit")
    units.resolve(rules, path)
    return path


def context(inp, config):
    inputs.check("context", inp)
    rules = rules_file.load(config)
    path = named_unit(rules, inp)
    manifest, warnings = units.check_manifest(rules, path)
    start = done = tasks = None
    if manifest is not None:
        kfolder = units.koan_folder(rules, path)
        try:
            found, koan_warnings = koan.list_tasks(kfolder, recursive=False, tags=())
        except OperationError as error:
            if error.kind != "koan-failed":
                raise
            warnings += units.koan_failed(error, path)
        else:
            start = units.match(found, kfolder, manifest["id"], "shingi-start")
            done = units.match(found, kfolder, manifest["id"], "shingi-done")
            warnings += units.missing_tasks(path, start, done) + koan_warnings
            tasks = [
                {k: t[k] for k in ("id", "title", "readiness", "blocking", "tags", "notes_path")}
                for t in sorted(found, key=lambda t: t["id"])
                if t["folder"] == kfolder and t["readiness"] != "done"
            ]
    parent = units.parent_of(path)
    segments = path.split("/")
    ancestors = []
    for i in range(1, len(segments)):
        ancestor = "/".join(segments[:i])
        folder = units.working_folder(rules, ancestor)
        try:
            ancestor_manifest = units.read_manifest(folder)
        except units.UnusableManifest:
            ancestor_manifest = None
        ancestors.append({
            "path": ancestor,
            "id": ancestor_manifest and ancestor_manifest["id"],
            "kind": ancestor_manifest and ancestor_manifest["kind"],
            "title": units.read_title(folder),
        })
    return {
        "unit": units.build_unit(rules, path, manifest, start, done),
        "ancestors": ancestors,
        "notes": units.read_notes(units.working_folder(rules, path)),
        "parent_notes": None if parent is None else units.read_notes(units.working_folder(rules, parent)),
        "tasks": tasks,
    }, units.sort_warnings(warnings)


def list_units(inp, config):
    inputs.check("list", inp)
    rules = rules_file.load(config)
    root = inp.get("unit")
    if root is not None:
        units.check_path(root, "/unit")
        units.resolve(rules, root)
    manifests, warnings = {}, []
    for path in units.walk(rules, root):
        manifests[path], problems = units.check_manifest(rules, path)
        warnings += problems
    by_id = {m["id"]: path for path, m in manifests.items() if m is not None}

    folder = rules.koan_root if root is None else units.koan_folder(rules, root)
    try:
        tasks, koan_warnings = koan.list_tasks(folder, recursive=True)
    except OperationError as error:
        if error.kind != "koan-failed":
            raise
        tasks, koan_warnings = None, units.koan_failed(error, None)
    warnings += koan_warnings
    found = []
    for path, manifest in manifests.items():
        unit, problems = units.unit_from(rules, path, manifest, tasks)
        found.append(unit)
        warnings += problems

    warnings += [orphan_task(rules, task, by_id) for task in tasks or [] if not claimed(rules, task, by_id)]
    return {"root": root, "units": found}, units.sort_warnings(warnings)


def claimed(rules, task, by_id):
    """Whether `task` is a start or done task of a unit list found, in that unit's koan folder."""
    path = by_id.get(task["extra"].get("shingi-unit"))
    return (
        path is not None
        and task["folder"] == units.koan_folder(rules, path)
        and task["extra"].get("source") in ("shingi-start", "shingi-done")
    )


def orphan_task(rules, task, by_id):
    extra = task["extra"]
    source, unit_id = extra.get("source"), extra.get("shingi-unit")
    return {
        "kind": "orphan-task",
        "message": f"task {task['id']} in {task['folder']} matches no unit",
        "unit": by_id.get(unit_id),
        "ids": [task["id"]],
        "details": {
            "folder": task["folder"],
            "source": source if isinstance(source, str) else None,
            "shingi_unit": unit_id if isinstance(unit_id, str) else None,
        },
    }


def create(inp, config):
    inputs.check("create", inp)
    return make_unit(inp, config, adopting=False)


def adopt(inp, config):
    inputs.check("adopt", inp)
    return make_unit(inp, config, adopting=True)


def delete(inp, config):
    """Make a unit a plain folder again: remove its koan folder, then its manifest."""
    inputs.check("delete", inp)
    rules = rules_file.load(config)
    loaded = hooks.load()
    path = inp["unit"]
    units.check_path(path, "/unit")
    units.resolve(rules, path)
    children = [child["path"] for child in units.children(rules, path)]
    if children:
        raise OperationError(
            "has-children", f"{path} has child units; delete those first", {"unit": path, "children": children}
        )
    kfolder, folder = units.koan_folder(rules, path), units.working_folder(rules, path)
    removed, warnings = koan.delete_folder(kfolder)
    manifest = folder / units.MANIFEST
    try:
        manifest.unlink(missing_ok=True)
    except OSError as exc:
        error = io_error(exc, manifest)
        error.warnings = warnings
        raise error
    result = {
        "path": path,
        "koan_folder": kfolder,
        "working_folder": str(folder),
        "tasks": sorted(removed["deleted"]) if removed else [],
        "unblocked": sorted(removed["dependents"]) if removed else [],
    }
    warnings = units.sort_warnings(warnings)
    warnings = units.sort_warnings(warnings + hooks.run(loaded, "delete", inp, result, warnings, unit=path))
    return result, warnings


def make_unit(inp, config, adopting):
    """create, or with `adopting`, adopt: they differ only in the working folder."""
    rules = rules_file.load(config)
    loaded = hooks.load()
    path, kind = inp["path"], inp["kind"]
    after = inp.get("after", [])  # create only: adopt's input has none
    check_unit(rules, inp, "", adopting)
    parent = units.parent_of(path)
    found, warnings = find_links(rules, [] if parent is None else [parent])
    after_found, koan_warnings = find_links(rules, after)
    found.update(after_found)
    warnings += koan_warnings + unlinked(path, parent, after, found)
    parent_start, parent_done_task, _ = found.get(parent, (None, None, None))
    after_done = [found[entry][1]["id"] for entry in after if found[entry][1] is not None]

    unit_id = str(uuid.uuid4())
    made = {"koan_folders": [], "tasks": [], "blocked": None, "files": []}
    try:
        write_unit(
            rules, inp, path, kind, unit_id, adopting, parent, parent_start, parent_done_task, after_done, made, warnings
        )
    except Exception as exc:
        raise with_partial(exc, made, warnings)
    unit, read_warnings = units.read_unit(rules, path)
    result = {"unit": unit}
    warnings = units.sort_warnings(warnings + read_warnings)
    event = "adopt" if adopting else "create"
    warnings = units.sort_warnings(warnings + hooks.run(loaded, event, inp, result, warnings, unit=path))
    return result, warnings


def check_unit(rules, inp, prefix, adopting=False, batch=frozenset(), listings=None):
    """create's checks, its steps 1.2 to 1.6, of one new unit, changing nothing. `prefix` is where
    its input is: "" for create's, "/units/<n>" for a create-batch entry; `batch` is the paths of
    the batch's units, counted as units though they aren't there yet; `listings`, the parent
    folders already listed, as check_entry keeps them."""
    path, kind = inp["path"], inp["kind"]
    after = inp.get("after", [])
    # From create-batch, an error about an entry says which, in `field`.
    at = {"field": f"{prefix}/path"} if prefix else {}
    units.check_path(path, f"{prefix}/path", creating=True)
    for index, entry in enumerate(after):
        units.check_path(entry, f"{prefix}/after/{index}")
    if kind not in rules.kinds:
        raise OperationError("unknown-kind", f"kind {kind!r} is not defined", {
            **({"field": f"{prefix}/kind"} if prefix else {}), "kind": kind, "defined": sorted(rules.kinds),
        })
    for index, entry in enumerate(after):
        relation = lineage(path, entry)
        if relation is not None:
            raise OperationError(
                "after-lineage",
                f"{path} can't come after {'itself' if relation == 'self' else f'its {relation} {entry}'}",
                {"field": f"{prefix}/after/{index}", "after": entry, "relation": relation},
            )
    parent = units.parent_of(path)
    if parent is not None:
        missing = missing_prefix(rules, parent, batch)
        if missing is not None:
            raise OperationError(
                "parent-not-found", f"parent {parent} is not a unit", {**at, "parent": parent, "missing": missing}
            )
    # A parent in the batch has no folder yet: its own check found that, and so nothing beneath it
    # can be in the way. Were that check ever to let a folder be there, this one must run again.
    if parent not in batch:
        check_entry(units.working_folder(rules, path), path, adopting, at, listings)
    for index, entry in enumerate(after):
        missing = missing_prefix(rules, entry, batch)
        if missing is not None:
            raise OperationError(
                "after-not-found",
                f"{entry} is not a unit",
                {"field": f"{prefix}/after/{index}", "after": entry, "missing": missing},
            )


def lineage(path, entry):
    """How `entry`, in the after of a new unit at `path`, is in its lineage, or None."""
    if entry == path:
        return "self"
    if path.startswith(entry + "/"):
        return "ancestor"
    if entry.startswith(path + "/"):
        return "descendant"
    return None


def missing_prefix(rules, path, batch):
    """The shortest prefix of `path` that is neither in `batch` nor a unit, or None."""
    segments = path.split("/")
    # A prefix is a unit only when every prefix before it is one, so those that are come first.
    for i in range(units.unit_depth(rules, path) + 1, len(segments) + 1):
        prefix = "/".join(segments[:i])
        if prefix not in batch:
            return prefix
    return None


def find_links(rules, paths):
    """The start and done tasks of each unit in `paths`, units already there, read in the order
    given: path -> (start, done, why a task not found wasn't), and koan's warnings. Raises
    koan-failed."""
    found, warnings = {}, []
    for path in paths:
        manifest, _ = units.check_manifest(rules, path)
        if manifest is None:
            found[path] = (None, None, "unsupported-manifest")
        else:
            start, done, koan_warnings = units.find_tasks(rules, path, manifest["id"])
            found[path] = (start, done, "missing-task")
            warnings += koan_warnings
    return found, warnings


def unlinked(path, parent, after, found):
    """The new unit's parent-unlinked and after-unlinked warnings: one for each link to a unit
    already there, in `found`, whose task wasn't found."""
    warnings = []
    if parent in found:
        start, done, reason = found[parent]
        for role, task in (("start", start), ("done", done)):
            if task is None:
                warnings.append(units.warning(
                    "parent-unlinked",
                    f"{parent}'s {role} task wasn't found, so {path} isn't linked to it",
                    path,
                    details={"parent": parent, "role": role, "reason": reason},
                ))
    for entry in after:
        if entry in found and found[entry][1] is None:
            warnings.append(units.warning(
                "after-unlinked",
                f"{entry}'s done task wasn't found, so {path} doesn't wait on it",
                path,
                details={"after": entry, "reason": found[entry][2]},
            ))
    return warnings


def unit_task(path, unit_id, role, blocked_by):
    """One of a new unit's two tasks, its `role` start or done."""
    return {
        "title": f"{role.capitalize()}: {path}",
        "tags": ["shingi", f"shingi-{role}"],
        "extra": {"source": f"shingi-{role}", "shingi-unit": unit_id},
        "blocked_by": blocked_by,
    }


def parent_done(parent, done, path):
    return units.warning(
        "parent-done",
        f"{parent}'s done task {done['id']} is already done, so {path} doesn't block it",
        path,
        [done["id"]],
        {"parent": parent},
    )


def write_unit(
    rules, inp, path, kind, unit_id, adopting, parent, parent_start, parent_done_task, after_done, made, warnings
):
    """create's steps 4 to 6: make the tasks, link the parent, write the files, recording in
    `made` what each step made."""
    try:
        batch, koan_warnings = koan.create_batch({
            "folder": units.koan_folder(rules, path),
            "tasks": [
                {"ref": "start", **unit_task(
                    path, unit_id, "start", ([parent_start["id"]] if parent_start else []) + after_done
                )},
                {"ref": "done", **unit_task(path, unit_id, "done", ["start"])},
            ],
        })
    except OperationError as error:
        koan_error = error.details.get("error") or {}
        if koan_error.get("changed_paths"):  # only then are its ids the tasks it made
            made["tasks"] = list(koan_error["ids"])
        raise
    made["koan_folders"] = list(batch["folders_created"])
    made["tasks"] = [batch["refs"]["start"], batch["refs"]["done"]]
    warnings += koan_warnings

    if parent_done_task and parent_done_task["readiness"] == "done":
        warnings.append(parent_done(parent, parent_done_task, path))
    elif parent_done_task:
        added = [batch["refs"]["done"]]
        _, koan_warnings = koan.block(parent_done_task["id"], added)
        made["blocked"] = {"task": parent_done_task["id"], "added": added}
        warnings += koan_warnings

    write_files(rules, inp, path, adopting, made["files"])
    write_manifest(path, units.working_folder(rules, path), {"schema": 1, "id": unit_id, "kind": kind})


def write_files(rules, inp, path, adopting, files, at=None):
    """create's steps 6.1 and 6.2: make the working folder, unless `adopting`, and create uow.md,
    adding to `files` each as it is made."""
    folder = units.working_folder(rules, path)
    if not adopting:
        try:
            if "/" not in path:
                rules.working_root.mkdir(parents=True, exist_ok=True)
            folder.mkdir()
        except FileExistsError:
            raise name_taken(path, folder.name, entry_type(folder), at)
        except OSError as exc:
            raise io_error(exc, folder)
        files.append(str(folder))
    title = inp.get("title") or path.rpartition("/")[2]
    notes = folder / units.NOTES
    try:
        with open(notes, "x", encoding="utf-8") as f:
            files.append(str(notes))
            f.write(notes_text(title, inp.get("notes", "")))
    except FileExistsError:
        pass
    except OSError as exc:
        raise io_error(exc, notes)


START, DONE = 0, 1  # a batch's task is (n, START) or (n, DONE), for the unit at position n


def create_batch(inp, config):
    """Make several units in one call (operations.md, create-batch)."""
    inputs.check("create-batch", inp)
    rules = rules_file.load(config)
    loaded = hooks.load()
    result, warnings = make_batch(rules, inp["units"]) if inp["units"] else ({"units": []}, [])
    warnings = units.sort_warnings(warnings + hooks.run(loaded, "create-batch", inp, result, warnings, unit=None))
    return result, warnings


def make_batch(rules, given):
    """create-batch's steps 1.2 to 6, for the units `given`, at least one: the result and its
    warnings, before the hooks run."""
    check_duplicates(given)
    numbered = sorted(enumerate(given), key=lambda item: units.path_key(item[1]["path"]))
    batch = {entry["path"] for entry in given}
    listings = {}  # each parent folder listed once, however many entries are made in it
    for index, entry in numbered:
        check_unit(rules, entry, f"/units/{index}", batch=batch, listings=listings)
    # From here a unit is known by its position n in path order.
    fields = [f"/units/{index}/path" for index, _ in numbered]
    entries = [entry for _, entry in numbered]
    paths = [entry["path"] for entry in entries]
    waits = batch_waits(entries, {path: n for n, path in enumerate(paths)})
    order = task_order(waits, paths)

    parents = {units.parent_of(path) for path in paths} - batch - {None}
    afters = {entry for unit in entries for entry in unit.get("after", [])} - batch
    found, warnings = find_links(rules, sorted(parents | afters, key=units.path_key))
    for entry in entries:
        warnings += unlinked(entry["path"], units.parent_of(entry["path"]), entry.get("after", []), found)

    made = {"units": [], "koan_folders": [], "tasks": {}, "blocked": [], "files": {}}
    try:
        write_batch(rules, entries, fields, waits, order, found, made, warnings)
    except Exception as exc:
        raise with_partial(exc, batch_partial(rules, paths, made), warnings)
    return read_batch(rules, paths, warnings)


def check_duplicates(entries):
    """No two entries' paths are the same, exactly or ignoring ASCII case (duplicate-path)."""
    seen = {}
    for index, entry in enumerate(entries):
        earlier = seen.setdefault(entry["path"].encode().lower(), index)  # bytes: ASCII case only
        if earlier != index:
            paths = [entries[earlier]["path"], entry["path"]]
            same = paths[0] == paths[1]
            raise OperationError(
                "duplicate-path",
                f"{paths[1]} is given twice" if same else f"{paths[0]} and {paths[1]} differ only in case",
                {
                    "fields": [f"/units/{earlier}/path", f"/units/{index}/path"],
                    "paths": paths,
                    "reason": "same" if same else "case",
                },
            )


def batch_waits(entries, position):
    """What each of the batch's tasks waits on in the batch: its parent's start task and the done
    task of each unit in its after, for a start task; its own start task and its children's done
    tasks, for a done task."""
    waits = {}
    for n, entry in enumerate(entries):
        parent = units.parent_of(entry["path"])
        waits[n, START] = [(position[parent], START)] if parent in position else []
        waits[n, START] += [(position[other], DONE) for other in entry.get("after", []) if other in position]
        waits[n, DONE] = [(n, START)]
    for n, entry in enumerate(entries):
        parent = units.parent_of(entry["path"])
        if parent in position:
            waits[position[parent], DONE].append((n, DONE))
    return waits


def task_order(waits, paths):
    """The batch's tasks in the order they are made: each time, of the tasks whose every wait is
    placed, the first in path order of its unit, start before done. Raises after-cycle."""
    waiting = {task: len(on) for task, on in waits.items()}
    dependents = {task: [] for task in waits}
    for task, on in waits.items():
        for other in on:
            dependents[other].append(task)
    ready = [task for task, count in waiting.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        task = heapq.heappop(ready)
        order.append(task)
        for other in dependents[task]:
            waiting[other] -= 1
            if waiting[other] == 0:
                heapq.heappush(ready, other)
    if len(order) < len(waits):
        raise after_cycle(waits, set(order), paths)
    return order


def after_cycle(waits, placed, paths):
    """after-cycle, with one cycle: from the first task left, each time the first of its waits
    left, until a task comes up again."""
    task, seen = min(task for task in waits if task not in placed), []
    while task not in seen:
        seen.append(task)
        task = min(other for other in waits[task] if other not in placed)
    cycle = []
    for n, _ in seen[seen.index(task):]:
        if not cycle or cycle[-1] != paths[n]:
            cycle.append(paths[n])
    if len(cycle) > 1 and cycle[-1] == cycle[0]:
        cycle.pop()
    return OperationError(
        "after-cycle",
        "the batch's afters can never all be met: " + " waits on ".join(cycle + cycle[:1]),
        {"cycle": cycle},
    )


def ref(task):
    """A batch task's ref in koan's create-batch: s<n> or d<n>."""
    n, role = task
    return f"{'sd'[role]}{n}"


def write_batch(rules, entries, fields, waits, order, found, made, warnings):
    """create-batch's steps 3 to 5: make the tasks, link the parents already there, write the
    files, recording in `made` what each step made, and for which unit."""
    paths = [entry["path"] for entry in entries]
    ids = [str(uuid.uuid4()) for _ in entries]
    tasks = []
    for n, role in order:
        entry, path = entries[n], paths[n]
        blocked_by = [ref(other) for other in waits[n, role]]
        if role == START:
            parent = units.parent_of(path)
            if parent in found and found[parent][0] is not None:
                blocked_by.append(found[parent][0]["id"])
            blocked_by += [
                found[other][1]["id"]
                for other in entry.get("after", [])
                if other in found and found[other][1] is not None
            ]
        tasks.append({
            "ref": ref((n, role)),
            "folder": units.koan_folder(rules, path),
            **unit_task(path, ids[n], ("start", "done")[role], blocked_by),
        })
    try:
        result, koan_warnings = koan.create_batch({"tasks": tasks})
    except OperationError as error:
        koan_error = error.details.get("error") or {}
        if koan_error.get("changed_paths"):  # only then are its ids the tasks it made
            made["tasks"].update(dict.fromkeys(koan_error["ids"]))  # no unit exists yet to keep them for
        raise
    warnings += koan_warnings
    made["koan_folders"] = list(result["folders_created"])
    task_ids = {task: result["refs"][ref(task)] for task in order}
    for task, task_id in task_ids.items():
        made["tasks"][task_id] = paths[task[0]]

    for parent in sorted({units.parent_of(path) for path in paths} & found.keys(), key=units.path_key):
        done = found[parent][1]
        if done is None:
            continue
        under = [n for n, path in enumerate(paths) if units.parent_of(path) == parent]
        if done["readiness"] == "done":
            warnings += [parent_done(parent, done, paths[n]) for n in under]
            continue
        added = [task_ids[n, DONE] for n in under]
        _, koan_warnings = koan.block(done["id"], added)
        made["blocked"].append({"task": done["id"], "added": added})
        warnings += koan_warnings

    for n, entry in enumerate(entries):
        write_files(rules, entry, paths[n], False, made["files"].setdefault(paths[n], []), {"field": fields[n]})
    # In start-task order, so a unit's manifest comes after its parent's and those of the units it
    # comes after: the units that exist are only ever linked to units that exist.
    for n, role in order:
        if role == START:
            manifest = {"schema": 1, "id": ids[n], "kind": entries[n]["kind"]}
            write_manifest(paths[n], units.working_folder(rules, paths[n]), manifest, {"field": fields[n]})
            made["units"].append(paths[n])


def batch_partial(rules, paths, made):
    """create-batch-partial: the units made, and what was made for the others."""
    kept = set(made["units"])
    kept_folders = [units.koan_folder(rules, path) for path in kept]
    tasks = sorted(task for task, path in made["tasks"].items() if path not in kept)
    left = set(tasks)
    blocked = []
    for link in sorted(made["blocked"], key=lambda link: link["task"]):
        added = [task for task in link["added"] if task in left]
        if added:
            blocked.append({"task": link["task"], "added": added})
    return {
        "units": made["units"],
        "koan_folders": [
            folder for folder in made["koan_folders"]
            if not any(other == folder or other.startswith(folder + "/") for other in kept_folders)
        ],
        "tasks": tasks,
        "blocked": blocked,
        "files": [file for path in paths if path not in kept for file in made["files"].get(path, [])],
    }


def read_batch(rules, paths, warnings):
    """create-batch's step 6: every new unit, read back from one koan list of the deepest koan
    folder that holds them all."""
    common = posixpath.commonpath(paths)
    folder = units.koan_folder(rules, common) if common else rules.koan_root
    try:
        tasks, koan_warnings = koan.list_tasks(folder, recursive=True)
    except OperationError as error:
        if error.kind != "koan-failed":
            raise
        tasks, koan_warnings = None, units.koan_failed(error, None)
    warnings = warnings + koan_warnings
    found = []
    for path in paths:
        manifest, problems = units.check_manifest(rules, path)
        unit, missing = units.unit_from(rules, path, manifest, tasks)
        found.append(unit)
        warnings += problems + missing
    return {"units": found}, units.sort_warnings(warnings)


def with_partial(exc, made, warnings):
    """`exc` as the error to report, with the warnings gathered before it and, when anything was
    made, `made` as its partial."""
    error = exc if isinstance(exc, OperationError) else OperationError(
        "internal", f"unexpected {type(exc).__name__}: {exc}"
    )
    error.warnings = units.sort_warnings(warnings + error.warnings)
    if any(made.values()):
        error.partial = made
    return error


def io_error(exc, path):
    return OperationError("io", f"{path}: {exc.strerror}", {"path": str(path), "code": errno.errorcode.get(exc.errno)})


def notes_text(title, notes):
    """uow.md as create writes it: the title, then, after a blank line, the notes, ending in a newline."""
    text = f"# {title}\n"
    if notes:
        text += "\n" + notes + ("" if notes.endswith("\n") else "\n")
    return text


def check_entry(folder, path, adopting, at=None, listings=None):
    """Check what is at the new unit's name in its parent's folder (operations.md, create step 1.5).
    `listings` keeps each parent folder's entries, listed once, for the next entry made in it."""
    name = folder.name
    listings = {} if listings is None else listings
    if folder.parent not in listings:
        # No working root yet: nothing is in it.
        listings[folder.parent] = sorted(
            folder.parent.iterdir() if folder.parent.exists() else [], key=lambda e: e.name.encode()
        )
    siblings = listings[folder.parent]
    # Only an entry named exactly so: on a case-insensitive filesystem, folder / MANIFEST finds another case's.
    if any(entry.name == name and (entry / units.MANIFEST).is_file() for entry in siblings):
        raise unit_exists(path, folder / units.MANIFEST, at)
    for entry in siblings:
        if entry.name.encode().lower() != name.encode().lower():  # ASCII case only
            continue
        # Only adopt may find something at the name: a folder with exactly it.
        if entry.name != name or not adopting or not entry.is_dir():
            raise name_taken(path, entry.name, entry_type(entry), at)
    if adopting and not folder.is_dir():
        raise OperationError(
            "not-found",
            f"there is no folder {path} to adopt",
            {"unit": path, "missing": path, "cwd": None, "reason": "no-folder"},
        )


def entry_type(entry):
    if not entry.is_dir():
        return "file"
    return "unit" if (entry / units.MANIFEST).is_file() else "folder"


def name_taken(path, entry, kind, at=None):
    return OperationError("name-taken", f"{entry} is in the way of {path}", {**(at or {}), "entry": entry, "type": kind})


def unit_exists(path, manifest, at=None):
    return OperationError("unit-exists", f"{path} already exists", {**(at or {}), "manifest": str(manifest)})


def write_manifest(path, folder, manifest, at=None):
    """Write uow.json once: a hidden temp file, flushed, then hard-linked into place. A temp file
    that can't be removed is left: it is hidden."""
    temp = folder / f".{units.MANIFEST}.{uuid.uuid4().hex}.tmp"
    target = folder / units.MANIFEST
    writing = temp
    try:
        with open(temp, "x", encoding="utf-8") as f:
            f.write(json.dumps(manifest, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        writing = target
        os.link(temp, target)
    except FileExistsError:
        raise unit_exists(path, target, at)
    except OSError as exc:
        raise io_error(exc, writing)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
