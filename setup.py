"""Include the static Studio in installed wheels without a JavaScript build step."""
from pathlib import Path
import shutil
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithStudio(build_py):
    def run(self):
        super().run()
        source = Path(__file__).parent / 'web'
        if source.is_dir():
            target = Path(self.build_lib) / 'prompt_skill_linter' / 'web'
            shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns('node_modules', '*.map', '__pycache__', 'tests', 'qa-artifacts'))


setup(cmdclass={'build_py': BuildWithStudio})
