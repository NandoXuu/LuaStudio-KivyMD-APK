-- 36: Calibracao de cor (Graphics.ColorCalibration) - SDR e HDR
-- Ordem: Black/White Point -> Contrast -> RGB Gain/Offset -> Highlights/Shadows
--        -> Saturation -> Brightness, antes do tone mapping/saida.
-- Teclas:  1/2/3 = visual do jogo (neutro / quente / frio)
--          Q/A = brilho do jogador   W/S = contraste   E/D = sombras (bloqueado!)
--          R = reseta os ajustes do jogador
app.background("#0b0f1a")

create.camera.Main = { Position = {0,3,-9}, Target = {0,0.5,0}, FOV = 70 }
create.light.Sol   = { Type = "directional", Direction = {-0.4,-0.9,-0.5}, Color = "#fff2dd", Intensity = 1.4 }
create.part.Chao   = { Shape = "plane",  Position = {0,-1,0}, Size = {12,1,12}, Color = "#2b3a5c" }
create.part.A      = { Shape = "cube",   Position = {-2.5,0.5,0}, Size = {1,1,1}, Color = "#e4572e" }
create.part.B      = { Shape = "sphere", Position = {0,0.5,0},    Size = {1,1,1}, Color = "#76b041" }
create.part.C      = { Shape = "pyramid",Position = {2.5,0.5,0},  Size = {1,1.4,1}, Color = "#29a1ff" }

local CC = Graphics.ColorCalibration
CC.Enabled = true

-- O jogo decide o que o jogador pode mexer. Sombras/pontos ficam travados
-- (estilo competitivo: ninguem enxerga no escuro com um slider).
CC.PlayerSettingsEnabled = true
CC.PlayerControls = {
    Brightness = true, Contrast = true, Saturation = true, RGBGain = true,
    BlackPoint = false, WhitePoint = false,
    Highlights = false, Shadows = false, RGBOffset = false,
}

local function look(name)
    CC.BlackPoint, CC.WhitePoint = 0.0, 1.0
    CC.Contrast, CC.Saturation = 1.0, 1.0
    CC.Highlights, CC.Shadows = 0.0, 0.0
    CC.RGB.Gain   = { R = 1, G = 1, B = 1 }
    CC.RGB.Offset = { R = 0, G = 0, B = 0 }
    if name == "quente" then
        CC.BlackPoint, CC.WhitePoint = 0.02, 0.98
        CC.Contrast, CC.Saturation = 1.10, 1.05
        CC.RGB.Gain = { R = 1.08, G = 1.00, B = 0.92 }
        CC.Highlights, CC.Shadows = 0.25, 0.10
    elseif name == "frio" then
        CC.Contrast, CC.Saturation = 1.15, 0.9
        CC.RGB.Gain = { R = 0.93, G = 1.00, B = 1.12 }
        CC.Shadows = 0.15
    end
end
look("neutro")

local brilho, contraste = 0, 1
local function status()
    local s = CC.GetStatus()
    return string.format("Ativo: %s | saida: %s | brilho %.2f | contraste %.2f",
        tostring(s.Active), s.Output, s.Brightness, s.Contrast)
end
create.label.HUD = { Text = status(), Position = {16,16}, Size = {620,32}, FontSize = 18, TextColor = "white" }

local K = input.keyboard
onUpdate(function(dt, t)
    if K.isPressed("1") then look("neutro") end
    if K.isPressed("2") then look("quente") end
    if K.isPressed("3") then look("frio") end
    if K.isDown("Q") then brilho = brilho + dt end
    if K.isDown("A") then brilho = brilho - dt end
    if K.isDown("W") then contraste = contraste + dt * 0.3 end
    if K.isDown("S") then contraste = contraste - dt * 0.3 end
    if K.isDown("E") then CC.Player.Shadows = 0.5 end   -- bloqueado: so avisa no log
    if K.isPressed("R") then brilho, contraste = 0, 1; CC.Player.Reset() end
    CC.Player.Brightness = brilho    -- limitados a +/-1.5 EV
    CC.Player.Contrast = contraste   -- limitado a 0.7..1.4
    app.find("B"):Rotate(0, 50*dt, 0)
    app.find("HUD").Text = status()
end)
