-- 34_skybox_6_faces_dia_noite.lua
-- Skybox cubica real: uma textura independente por face.
Env3D.set({
    SkyTop = "#39205e", SkyBottom = "#ff9b70",
    SkyboxEnabled = true,
    SkyboxSize = 1000,
    SkyboxRight = "assets/skybox6/right.png",
    SkyboxLeft = "assets/skybox6/left.png",
    SkyboxTop = "assets/skybox6/top.png",
    SkyboxBottom = "assets/skybox6/bottom.png",
    SkyboxFront = "assets/skybox6/front.png",
    SkyboxBack = "assets/skybox6/back.png",
    DayNight = true,
    DayLength = 300,
    WorldTime = 0.22,
    SunEnabled = true,
    SunTexture = "assets/engine/sun.png",
    SunSize = 112,
    SunOrbit = true,
    SunIntensity = 1.0,
    Ambient = 0.35,
    FogColor = "#6e416f",
    FogDensity = 0.0015
})

-- A API Sun controla o sprite e o relogio solar sem mexer no resto do ambiente.
Sun.setTexture("assets/engine/sun.png")
Sun.setSize(112)
Sun.enable(true)
Sun.setOrbit(true)
-- Sun.setTime(0.22) -- 0..1 representa o ciclo completo; descomente para fixar a hora.

create.camera.Main {
    Position = {0, 2, -8},
    Target = {0, 2, 0},
    FOV = 70
}

create.part.Ground {
    Shape = "plane", Position = {0, -0.2, 0},
    Size = {120, 1, 120}, Color = "#34243f"
}
create.part.Cube {
    Shape = "cube", Position = {0, 1, 4},
    Size = {2, 2, 2}, Color = "#ff9b70"
}
