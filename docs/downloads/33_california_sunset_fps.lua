-- 33_california_sunset_fps.lua
-- Por do sol californiano: ceu gradiente, sol visivel e camera em primeira pessoa.
-- Controles touch: arraste o lado direito para olhar; arraste o lado esquerdo para andar.
-- Teclado opcional: WASD para andar (se a plataforma enviar essas teclas ao Input).

app.background("#ff9368")
Env3D.set({
    SkyTop = "#54256f",       -- roxo ameixa no alto (fallback sem textura)
    SkyBottom = "#ff9566",    -- laranja quente no horizonte (fallback sem textura)
    SkyTexture = "assets/skybox_california.png", -- panorama customizavel
    SkyScale = 1.0,
    SkyWidth = 1.0,
    SkyHeight = 1.0,
    SkyOffsetX = 0.0,
    SkyOffsetY = 0.0,
    SunTexture = "assets/engine/sun.png",
    SunSize = 112,
    SunEnabled = true,
    SunOrbit = true,
    FogColor = "#df7898",     -- rosa da bruma distante
    FogStart = 22,
    FogEnd = 95,
    FogDensity = 0.008,
    Ambient = 0.52,
    SunDirection = {-0.35, -0.75, 0.55},
    SunIntensity = 0.95,
    SunColor = "#ffd6a0",
    DayNight = true,
    DayLength = 300, -- ciclo completo em 5 minutos
    WorldTime = 0.20 -- hora inicial: tarde dourada (0..1 = dia completo)
})

local cam = create.camera.Main {
    Position = {0, 1.7, -5},
    Target = {0, 1.7, 0},
    FOV = 74
}

-- Sol baixo no horizonte, grande e quente.
create.part.Sol = {
    Shape = "sphere", Position = {0, 7.2, 42},
    Size = {5.2, 5.2, 5.2}, Color = "#ffd27b"
}

-- Chao escuro para silhuetas de costa/deserto.
create.part.Chao = {
    Shape = "plane", Position = {0, -0.15, 35},
    Size = {180, 1, 180}, Color = "#34243f"
}

-- Silhuetas simples de montanhas nas laterais.
create.part.MontanhaE = {
    Shape = "pyramid", Position = {-13, 2.0, 28},
    Size = {18, 7, 20}, Color = "#58304f"
}
create.part.MontanhaD = {
    Shape = "pyramid", Position = {15, 2.6, 35},
    Size = {22, 9, 24}, Color = "#472846"
}
create.part.PalmeiraTronco = {
    Shape = "cylinder", Position = {6, 2.2, 15},
    Size = {0.35, 4.5, 0.35}, Color = "#33232f"
}
create.part.PalmeiraCopa1 = {
    Shape = "pyramid", Position = {6, 4.8, 15},
    Size = {2.8, 1.0, 1.2}, Color = "#292a38"
}

local px, py, pz = 0, 1.7, -5
local yaw, pitch = 0, 0
local touchId, touchMode = nil, nil
local lastX, lastY = 0, 0
local function limitar(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end
local function atualizarCamera()
    local cp = math.cos(pitch)
    cam.Position = vec3(px, py, pz)
    cam.Target = vec3(px + math.sin(yaw) * cp,
                       py + math.sin(pitch),
                       pz + math.cos(yaw) * cp)
end
atualizarCamera()

onTouch(function(x, y, phase, uid)
    local largura = app.width()
    if phase == "down" and touchId == nil then
        touchId = uid
        lastX, lastY = x, y
        -- lado esquerdo: movimento; lado direito: olhar ao redor
        touchMode = (x < largura * 0.42) and "move" or "look"
    elseif touchId == uid and phase == "move" then
        local dx, dy = x - lastX, y - lastY
        lastX, lastY = x, y
        if touchMode == "look" then
            yaw = yaw - dx * 0.0045
            pitch = limitar(pitch - dy * 0.0035, -1.15, 1.15)
        elseif touchMode == "move" then
            local frente = -dy * 0.035
            local lado = dx * 0.025
            px = px + math.sin(yaw) * frente + math.cos(yaw) * lado
            pz = pz + math.cos(yaw) * frente - math.sin(yaw) * lado
        end
        atualizarCamera()
    elseif touchId == uid and (phase == "up" or phase == "cancel") then
        touchId, touchMode = nil, nil
    end
end)

-- Luzes de preenchimento suaves para objetos na cena.
create.light.SolLuz = {
    Type = "directional", Direction = {-0.35, -0.75, 0.55},
    Color = "#ffb17c", Intensity = 0.8, Enabled = true
}

create.label.Dica = {
    Text = "CALIFORNIA DREAMIN'  |  toque esquerdo: andar  |  toque direito: olhar",
    Position = {14, 14}, Size = {440, 30}, FontSize = 15,
    TextColor = "#fff0df"
}
