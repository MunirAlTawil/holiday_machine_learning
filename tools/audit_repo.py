#!/usr/bin/env python3
"""
Repository Audit Script for Holiday Itinerary Project
Automatically inspects the repository and generates an audit summary JSON.
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any

def find_files(pattern: str, root: Path = None) -> List[Path]:
    """Find files matching pattern recursively."""
    if root is None:
        root = Path(__file__).parent.parent
    return list(root.rglob(pattern))

def detect_docker_files(root: Path) -> Dict[str, Any]:
    """Detect Docker-related files."""
    dockerfiles = find_files("Dockerfile*", root)
    compose_files = find_files("docker-compose*.yml", root) + find_files("docker-compose*.yaml", root)
    
    services = {}
    ports = []
    
    for compose_file in compose_files:
        try:
            with open(compose_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Extract service names
                service_pattern = r'^\s+(\w+):'
                services_found = re.findall(service_pattern, content, re.MULTILINE)
                services[compose_file.name] = services_found
                
                # Extract ports
                port_pattern = r'"(\d+):(\d+)"'
                ports_found = re.findall(port_pattern, content)
                ports.extend([f"{p[0]}:{p[1]}" for p in ports_found])
        except Exception as e:
            pass
    
    return {
        "dockerfiles": [str(f.relative_to(root)) for f in dockerfiles],
        "compose_files": [str(f.relative_to(root)) for f in compose_files],
        "services": services,
        "ports": list(set(ports))
    }

def detect_fastapi_endpoints(api_file: Path) -> List[str]:
    """Detect FastAPI endpoints by parsing main.py."""
    endpoints = []
    try:
        with open(api_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Find @app.get, @app.post, @app.put, @app.delete decorators
            pattern = r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
            matches = re.findall(pattern, content)
            endpoints = [f"{method.upper()} {path}" for method, path in matches]
    except Exception as e:
        pass
    return endpoints

def detect_pipelines(root: Path) -> Dict[str, Any]:
    """Detect ETL pipelines and scheduling configuration."""
    pipeline_files = find_files("*pipeline*.py", root)
    batch_etl = find_files("batch_etl.py", root)
    scheduler_files = find_files("crontab", root) + find_files("*scheduler*", root)
    
    cron_configs = []
    for cron_file in scheduler_files:
        try:
            with open(cron_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if '0 * * * *' in content or 'cron' in content.lower():
                    cron_configs.append(str(cron_file.relative_to(root)))
        except:
            pass
    
    airflow_configs = find_files("dag*.py", root) + find_files("airflow*.yml", root)
    jenkins_configs = find_files("Jenkinsfile", root)
    
    return {
        "pipeline_files": [str(f.relative_to(root)) for f in pipeline_files],
        "batch_etl_files": [str(f.relative_to(root)) for f in batch_etl],
        "cron_configs": cron_configs,
        "airflow_configs": [str(f.relative_to(root)) for f in airflow_configs],
        "jenkins_configs": [str(f.relative_to(root)) for f in jenkins_configs]
    }

def detect_ci_cd(root: Path) -> Dict[str, Any]:
    """Detect CI/CD configuration files."""
    github_workflows = find_files(".github/workflows/*.yml", root) + find_files(".github/workflows/*.yaml", root)
    gitlab_ci = find_files(".gitlab-ci.yml", root)
    circleci = find_files(".circleci/config.yml", root)
    jenkins = find_files("Jenkinsfile", root)
    
    ci_files = github_workflows + gitlab_ci + circleci + jenkins
    
    workflows = {}
    for ci_file in ci_files:
        try:
            with open(ci_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Check for common CI patterns
                has_lint = 'lint' in content.lower() or 'flake8' in content.lower() or 'pylint' in content.lower()
                has_test = 'test' in content.lower() or 'pytest' in content.lower()
                has_build = 'build' in content.lower() or 'docker build' in content.lower()
                has_deploy = 'deploy' in content.lower() or 'release' in content.lower()
                
                workflows[str(ci_file.relative_to(root))] = {
                    "has_lint": has_lint,
                    "has_test": has_test,
                    "has_build": has_build,
                    "has_deploy": has_deploy
                }
        except:
            pass
    
    return {
        "ci_files": [str(f.relative_to(root)) for f in ci_files],
        "workflows": workflows
    }

def analyze_readme(readme_file: Path) -> Dict[str, Any]:
    """Analyze README completeness."""
    sections = {
        "overview": False,
        "setup": False,
        "usage": False,
        "api_docs": False,
        "architecture": False,
        "docker": False,
        "ci_cd": False,
        "contributing": False
    }
    
    try:
        with open(readme_file, 'r', encoding='utf-8') as f:
            content = f.read().lower()
            
            sections["overview"] = any(word in content for word in ["overview", "description", "about"])
            sections["setup"] = any(word in content for word in ["setup", "install", "prerequisites"])
            sections["usage"] = any(word in content for word in ["usage", "how to run", "example"])
            sections["api_docs"] = any(word in content for word in ["api", "endpoint", "swagger"])
            sections["architecture"] = any(word in content for word in ["architecture", "diagram", "design"])
            sections["docker"] = any(word in content for word in ["docker", "container", "compose"])
            sections["ci_cd"] = any(word in content for word in ["ci/cd", "ci", "cd", "github actions", "workflow"])
            sections["contributing"] = any(word in content for word in ["contributing", "contribute", "development"])
    except:
        pass
    
    return sections

def detect_architecture_docs(root: Path) -> List[str]:
    """Detect architecture diagrams and documentation."""
    image_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.pdf']
    diagram_files = []
    
    for ext in image_extensions:
        diagram_files.extend(find_files(f"*{ext}", root))
    
    # Also check for draw.io files
    diagram_files.extend(find_files("*.drawio", root))
    
    # Filter to likely architecture docs
    architecture_keywords = ['arch', 'diagram', 'design', 'uml', 'flow', 'structure']
    filtered = []
    for f in diagram_files:
        name_lower = f.name.lower()
        if any(keyword in name_lower for keyword in architecture_keywords):
            filtered.append(str(f.relative_to(root)))
    
    return filtered

def detect_database_schema(root: Path) -> Dict[str, Any]:
    """Detect database schema files."""
    sql_files = find_files("*.sql", root)
    schema_files = [f for f in sql_files if 'schema' in f.name.lower() or 'init' in f.name.lower()]
    migration_files = [f for f in sql_files if 'migration' in f.name.lower() or 'migrate' in f.name.lower()]
    
    return {
        "sql_files": [str(f.relative_to(root)) for f in sql_files],
        "schema_files": [str(f.relative_to(root)) for f in schema_files],
        "migration_files": [str(f.relative_to(root)) for f in migration_files]
    }

def detect_tests(root: Path) -> Dict[str, Any]:
    """Detect test files."""
    test_files = find_files("test_*.py", root) + find_files("*_test.py", root)
    test_dirs = [d for d in root.rglob("tests") if d.is_dir()]
    
    return {
        "test_files": [str(f.relative_to(root)) for f in test_files],
        "test_directories": [str(d.relative_to(root)) for d in test_dirs]
    }

def main():
    """Main audit function."""
    root = Path(__file__).parent.parent
    
    # Detect components
    docker_info = detect_docker_files(root)
    
    # Find API file
    api_files = find_files("**/api/main.py", root)
    endpoints = []
    if api_files:
        endpoints = detect_fastapi_endpoints(api_files[0])
    
    pipeline_info = detect_pipelines(root)
    ci_cd_info = detect_ci_cd(root)
    
    # Find README
    readme_files = find_files("README.md", root)
    readme_analysis = {}
    if readme_files:
        readme_analysis = analyze_readme(readme_files[0])
    
    architecture_docs = detect_architecture_docs(root)
    db_schema = detect_database_schema(root)
    tests = detect_tests(root)
    
    # Compile audit summary
    audit_summary = {
        "project_name": "Holiday Itinerary",
        "audit_date": str(Path(__file__).stat().st_mtime),
        "docker": docker_info,
        "api": {
            "main_file": str(api_files[0].relative_to(root)) if api_files else None,
            "endpoints": endpoints,
            "endpoint_count": len(endpoints)
        },
        "pipelines": pipeline_info,
        "ci_cd": ci_cd_info,
        "readme": readme_analysis,
        "architecture_docs": architecture_docs,
        "database": db_schema,
        "tests": tests
    }
    
    # Write to docs/AUDIT_SUMMARY.json
    docs_dir = root / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    output_file = docs_dir / "AUDIT_SUMMARY.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(audit_summary, f, indent=2, ensure_ascii=False)
    
    print(f"Audit summary written to {output_file}")
    return audit_summary

if __name__ == "__main__":
    main()


