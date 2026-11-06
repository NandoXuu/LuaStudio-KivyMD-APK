from os.path import join, exists
from pythonforandroid.recipes.pygame import Pygame2Recipe
from pythonforandroid.toolchain import current_directory


class Pygame261Recipe(Pygame2Recipe):
    version = "2.6.1"
    url = "https://github.com/pygame/pygame/archive/{version}.tar.gz"
    hostpython_prerequisites = ["setuptools", "cython>=3.1"]

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)

        with current_directory(self.get_build_dir(arch.arch)):
            # Remove o modulo Cython opcional que falha com Cython 3.1
            sprite_pyx = join(
                "src_c", "cython", "pygame", "_sprite.pyx"
            )

            if exists(sprite_pyx):
                import os
                os.remove(sprite_pyx)
                print("[Pygame recipe] Removido _sprite.pyx")

            # Remove a entrada _sprite dos arquivos Setup
            for filename in [
                join("buildconfig", "Setup.Android.SDL2.in"),
                "Setup",
            ]:
                if not exists(filename):
                    continue

                with open(filename, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                filtered_lines = []
                removed = []

                for line in lines:
                    stripped = line.lstrip()

                    if (
                        stripped.startswith("_sprite ")
                        or "src_c/_sprite.c" in line
                        or "pygame._sprite" in line
                        or "_sprite.pyx" in line
                    ):
                        removed.append(line.strip())
                        continue

                    filtered_lines.append(line)

                with open(filename, "w", encoding="utf-8") as f:
                    f.writelines(filtered_lines)

                if removed:
                    print(
                        f"[Pygame recipe] {filename}: "
                        f"removido: {removed}"
                    )


recipe = Pygame261Recipe()
