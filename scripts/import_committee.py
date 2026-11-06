"""Import application-only source and the tested standalone release, never account/config data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"package.json", "pnpm-lock.yaml", "bun.lock", "next.config.ts", "postcss.config.mjs",
              "tailwind.config.ts", "tsconfig.json", "tsconfig.app-check.json", "components.json", "eslint.config.mjs",
              "scripts/train-stock-forecast.py", "scripts/prepare-stock-forecast.py", "scripts/verify-stock-forecast.mjs"}
EXCLUDED = {"heldout", "private_test", "evaluation", "db", "upload", "uploads", ".git", "__pycache__"}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def allowed(path: Path) -> bool:
    private_suffixes=('.db','.sqlite','.sqlite3','.db-wal','.db-shm','.sqlite-wal','.sqlite-shm','.pem','.key','.p12','.pfx','.pdf')
    return not path.name.lower().endswith(private_suffixes) and not any(
        part.lower() in EXCLUDED or part.lower().startswith(".env") for part in path.parts)


def walk(root: Path, permitted_roots: tuple[Path, ...] = (), ancestors: tuple[Path, ...] = ()):
    # Standalone packages use junctions. Materialize only approved dependency roots.
    resolved = root.resolve()
    if resolved in ancestors:
        return
    for entry in sorted(root.iterdir()):
        if not allowed(Path(entry.name)):
            continue
        if entry.is_symlink() or entry.is_junction():
            if not any(entry.resolve().is_relative_to(base) for base in permitted_roots):
                continue
        if entry.is_dir():
            yield from walk(entry, permitted_roots, (*ancestors, resolved))
        elif entry.is_file():
            yield entry


def package_dependencies(package: Path, destination: Path, dependency_root: Path, chain: tuple[Path, ...] = ()):
    """Junction realpaths resolve pnpm sibling dependencies; materialize that closure locally."""
    package = package.resolve()
    if package in chain:
        return
    metadata = package / 'package.json'
    if not metadata.is_file():
        return
    config = json.loads(metadata.read_text(encoding='utf-8'))
    if config.get('name') == '@prisma/client':
        yield from generated_prisma_files(package, destination, dependency_root)
    peers={name for name in config.get('peerDependencies',{}) if not config.get('peerDependenciesMeta',{}).get(name,{}).get('optional',False)}
    names = set(config.get('dependencies', {})) | set(config.get('optionalDependencies', {})) | peers
    for name in sorted(names):
        if not re.fullmatch(r'(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_.-]+', name):
            raise ValueError('Invalid dependency name')
        found = None
        for ancestor in (package, *package.parents):
            candidate = ancestor / 'node_modules' / name
            if candidate.is_dir() and candidate.resolve().is_relative_to(dependency_root):
                found = candidate.resolve()
                break
            if ancestor == dependency_root.parent:
                break
        if found is None or found in (*chain, package):
            continue  # Optional packages may be absent; cycles resolve to an ancestor package.
        target = destination / 'node_modules' / name
        for file in walk(found, (dependency_root,)):
            yield file, target / file.relative_to(found)
        yield from package_dependencies(found, target, dependency_root, (*chain, package))


def generated_prisma_files(package: Path, destination: Path, dependency_root: Path):
    package = package.resolve()
    for ancestor in package.parents:
        if ancestor.name == 'node_modules':
            generated = ancestor / '.prisma/client'
            if generated.is_dir() and generated.resolve().is_relative_to(dependency_root):
                for file in walk(generated, (dependency_root,)):
                    yield file, destination / 'node_modules/.prisma/client' / file.relative_to(generated)
                return
        if ancestor == dependency_root:
            break


def import_snapshot(source: Path, runtime: Path, project: Path, build_name: str) -> dict:
    source, runtime, project = source.resolve(), runtime.resolve(), project.resolve()
    if not re.fullmatch(r"\.next(?:[-a-zA-Z0-9]+)?", build_name):
        raise ValueError("Invalid standalone build directory")
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a in (source, runtime) for b in (project,)):
        raise ValueError("Source/runtime and destination must not overlap")
    build_file = runtime / build_name / "BUILD_ID"
    if not build_file.is_file() or not (runtime / "server.js").is_file():
        raise ValueError("Standalone build identity is required")
    build_id = build_file.read_text(encoding="utf-8").strip()
    if not build_id or len(build_id) > 120:
        raise ValueError("Invalid build ID")
    transfers = []
    source_hashes, runtime_hashes, source_bytes, runtime_bytes = {}, {}, 0, 0
    for name in ("src", "public", "prisma", *sorted(ROOT_FILES)):
        location = source / name
        paths = list(walk(location)) if location.is_dir() else [location] if location.is_file() else []
        for path in paths:
            relative = path.relative_to(source)
            if not allowed(relative):
                continue
            checksum = sha(path)
            source_hashes[relative.as_posix()] = checksum
            source_bytes += path.stat().st_size
            transfers.append((path, project / "apps/committee" / relative, checksum))
    for name in ("server.js", "package.json", build_name, "node_modules", "public", "src"):
        location = runtime / name
        paths = list(walk(location, (runtime, (source / "node_modules").resolve()))) if location.is_dir() else [location] if location.is_file() else []
        for path in paths:
            relative = path.relative_to(runtime)
            if not allowed(relative):
                continue
            checksum = sha(path)
            runtime_hashes[relative.as_posix()] = checksum
            runtime_bytes += path.stat().st_size
            transfers.append((path, project / ".local/committee/runtime" / relative, checksum))
    for link in (runtime / 'node_modules').rglob('*') if (runtime / 'node_modules').exists() else []:
        if (link.is_symlink() or link.is_junction()) and link.is_dir() and (link / 'package.json').is_file():
            dependency_root = (source / 'node_modules').resolve()
            if not link.resolve().is_relative_to(dependency_root):
                continue
            relative_package = link.relative_to(runtime)
            for path, relative in package_dependencies(link, relative_package, dependency_root):
                key = relative.as_posix()
                if key in runtime_hashes:
                    continue
                checksum = sha(path)
                runtime_hashes[key] = checksum
                runtime_bytes += path.stat().st_size
                transfers.append((path, project / '.local/committee/runtime' / relative, checksum))
    for target in [*(entry[1] for entry in transfers),project/'.local/committee/runtime-files.json',project/'integrations/committee-manifest.json']:
        if not target.resolve().is_relative_to(project):
            raise ValueError('Unsafe destination parent link')
    for _, target, checksum in transfers:
        if target.is_symlink() or target.is_junction():
            raise ValueError(f"Changed destination link: {target.name}")
        if target.exists() and sha(target) != checksum:
            raise ValueError(f"Changed destination; refusing overwrite: {target.name}")
    for path, target, _ in transfers:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    runtime_index = project / ".local/committee/runtime-files.json"
    runtime_index.parent.mkdir(parents=True, exist_ok=True)
    runtime_index.write_text(json.dumps(runtime_hashes, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    pages = sorted("/" + name.removeprefix("src/app/").removesuffix("/page.tsx")
                   if name != "src/app/page.tsx" else "/" for name in source_hashes if name.endswith("/page.tsx"))
    routes = sorted("/" + name.removeprefix("src/app/").removesuffix("/route.ts")
                    for name in source_hashes if name.endswith("/route.ts"))
    manifest = {"schema_version": "committee-integration-v1", "release": "DeepSeekFlash-DecisionNewsFix-20261018",
                "build_id": build_id, "build_directory": build_name, "source_root": str(source),
                "runtime_source_root": str(runtime), "source_files": source_hashes,
                "source_bytes": source_bytes, "runtime_file_count": len(runtime_hashes), "runtime_bytes": runtime_bytes,
                "runtime_index_sha256": sha(runtime_index), "pages": pages, "api_routes": routes,
                "secrets_copied": False, "account_database_copied": False,
                "integration": "complete isolated Next application plus native M1 scenario tools"}
    destination = project / "integrations/committee-manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def package_local_build(project: Path, build_name: str, release: str) -> dict:
    """Stage a new local release; retain upstream provenance and all account bindings."""
    project = project.resolve()
    if not re.fullmatch(r'\.next(?:[-a-zA-Z0-9]+)?', build_name):
        raise ValueError('Invalid build directory')
    source = project / 'apps/committee'
    standalone = source / build_name / 'standalone'
    build_id = (standalone / build_name / 'BUILD_ID').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}', build_id):
        raise ValueError('Invalid build identity')
    local = project / '.local/committee'
    destination = local / 'releases' / build_id
    if not destination.resolve().is_relative_to(project) or destination.exists():
        raise ValueError('Release destination must be new and inside the project')
    config_path = local / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    manifest_path = project / 'integrations/committee-manifest.json'
    upstream_path = project / 'integrations/committee-upstream-manifest.json'
    upstream_bytes = (upstream_path if upstream_path.exists() else manifest_path).read_bytes()
    upstream = json.loads(upstream_bytes)
    # Next standalone deliberately omits these assets. Copy only public, filtered files.
    for origin, target in ((source / 'public', standalone / 'public'),
                           (source / build_name / 'static', standalone / build_name / 'static')):
        for file in walk(origin):
            output = target / file.relative_to(origin)
            if not output.resolve().is_relative_to(standalone.resolve()):
                raise ValueError('Unsafe asset destination')
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, output)
    with tempfile.TemporaryDirectory(prefix='package-', dir=local) as folder:
        stage = Path(folder)
        result = import_snapshot(source, standalone, stage, build_name)
        staged_runtime = stage / '.local/committee/runtime'
        index = stage / '.local/committee/runtime-files.json'
        hashes = json.loads(index.read_text(encoding='utf-8'))
        # Explicit server externals may be omitted by tracing on Windows/pnpm.
        # Complete their closure in the materialized stage, never through source junctions.
        dependency_root = (source / 'node_modules').resolve()
        for name in ('pdf-parse', 'pdfjs-dist', '@prisma/client'):
            package = source / 'node_modules' / name
            if not package.is_dir():
                continue
            target = staged_runtime / 'node_modules' / name
            transfers = [(file, target / file.relative_to(package.resolve())) for file in walk(package.resolve(), (dependency_root,))]
            transfers.extend(package_dependencies(package, target, dependency_root))
            for file, output in transfers:
                if not output.resolve().is_relative_to(staged_runtime):
                    raise ValueError('Unsafe external dependency destination')
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, output)
                hashes[output.relative_to(staged_runtime).as_posix()] = sha(output)
        index.write_text(json.dumps(hashes, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        result.update(runtime_file_count=len(hashes), runtime_bytes=sum((staged_runtime / name).stat().st_size for name in hashes), runtime_index_sha256=sha(index))
        result.update(release=release, upstream_release=upstream['release'], upstream_build_id=upstream['build_id'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not staged_runtime.resolve().is_relative_to(project):
            raise ValueError('Unsafe staged runtime')
        shutil.move(str(staged_runtime), str(destination))
        # All expensive copying/checks finished before updating the active local binding.
        if not upstream_path.exists():
            upstream_path.write_bytes(upstream_bytes)
        previous = local / 'previous-release'
        previous.mkdir(exist_ok=True)
        for current in (config_path, manifest_path, local / 'runtime-files.json'):
            if current.exists():
                shutil.copyfile(current, previous / current.name)
        shutil.copyfile(stage / '.local/committee/runtime-files.json', local / 'runtime-files.json')
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        config['runtimeDir'] = str(destination)
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("D:/北大金融比赛/模型统一_DeepSeekFlash_20261018/app"))
    parser.add_argument("--runtime", type=Path, default=Path("D:/北大金融比赛/模型统一_DeepSeekFlash_20261018/app/.next-decision-display/standalone"))
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--build-name", default=".next-decision-display")
    parser.add_argument("--local-build", action='store_true', help='Package apps/committee standalone build, preserving original data bindings')
    parser.add_argument("--release", default='Local-Committee-Build')
    args = parser.parse_args()
    result = package_local_build(args.project, args.build_name, args.release) if args.local_build else import_snapshot(args.source, args.runtime, args.project, args.build_name)
    print(json.dumps({key: result[key] for key in ("release", "build_id", "runtime_file_count", "runtime_bytes", "pages", "api_routes")}, ensure_ascii=False, indent=2))
