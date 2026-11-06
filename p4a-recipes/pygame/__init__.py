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
            # Remove o módulo Cython opcional que falha
            sprite_pyx = join("src_c", "cython", "pygame", "_sprite.pyx")

            if exists(sprite_pyx):
                import os
                os.remove(sprite_pyx)

            # Remove a referência do template e do Setup gerado
            for filename in [
                join("buildconfig", "Setup.Android.SDL2.in"),
                "Setup",
            ]:
                if not exists(filename):
                    continue

                with open(filename, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                lines = [
                    line for line in lines
                    if "pygame._sprite" not in line
                    and "_sprite.pyx" not in line
                ]

                with open(filename, "w", encoding="utf-8") as f:
                    f.writelines(lines)


recipe = Pygame261Recipe()
