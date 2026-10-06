from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path

    @classmethod
    def from_source(cls, source: str | Path) -> "ProjectPaths":
        current = Path(source).resolve()
        if current.is_file():
            current = current.parent

        for candidate in (current, *current.parents):
            if (candidate / "pyproject.toml").is_file():
                return cls(root=candidate)

        raise FileNotFoundError(
            f"Could not find the project root above {current}"
        )

    @property
    def queries(self) -> Path:
        return self.root / "data_access" / "queries"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    def query(self, filename: str) -> Path:
        return self.queries / filename

    def artifact(self, filename: str) -> Path:
        return self.artifacts / filename


project_path = ProjectPaths.from_source(__file__)
