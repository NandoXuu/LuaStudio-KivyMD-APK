-- 35: HDR (Graphics.HDR)
-- Em HDR10 o branco de papel (SDR) fica em PaperWhiteNits e tudo que passa de
-- 1.0 na cena (Emissive, luzes fortes, ExpandHighlights) vai ate PeakLuminanceNits.
app.background("#05070d")

if Graphics.HDR.IsSupported() then
    Graphics.HDR.Enabled = true
    Graphics.HDR.Output = "HDR10"
else
    Graphics.HDR.Enabled = false
end

Graphics.HDR.ColorSpace = "BT2020"
Graphics.HDR.TransferFunction = "PQ"
Graphics.HDR.PaperWhiteNits = 203
Graphics.HDR.PeakLuminanceNits = 1000
Graphics.HDR.ToneMapping = "ACES"

Graphics.HDR.Metadata.MaxCLL = 1000
Graphics.HDR.Metadata.MaxFALL = 300

create.camera.Main = { Position = {0,3,-9}, Target = {0,0.5,0}, FOV = 70 }
create.light.Sol   = { Type = "directional", Direction = {-0.4,-0.9,-0.5}, Color = "#fff2dd", Intensity = 2.5 }

create.part.Chao   = { Shape = "plane",  Position = {0,-1,0},   Size = {12,1,12}, Color = "#1c2740" }
create.part.Lampada = { Shape = "sphere", Position = {-2.5,0.5,0}, Size = {1,1,1}, Color = "#ffd27a", Emissive = 3.5 }
create.part.Neon   = { Shape = "cube",   Position = {0,0.5,0},   Size = {1,1,1}, Color = "#4aa3ff", Emissive = 2.0 }
create.part.Lava   = { Shape = "pyramid", Position = {2.5,0.5,0}, Size = {1,1.4,1}, Color = "#ff5a1f", Emissive = 4.0 }

local st = Graphics.HDR.GetStatus()
create.label.HUD = { Text = "Modo: " .. st.Mode .. "  |  pico: " .. math.floor(st.PeakLuminanceNits) .. " nits",
                     Position = {16,16}, Size = {420,36}, FontSize = 20, TextColor = "white" }

onUpdate(function(dt, t)
    app.find("Neon"):Rotate(40*dt, 60*dt, 0)
    app.find("Lava"):Rotate(0, 80*dt, 0)
    app.find("Lampada").Emissive = 2.5 + math.sin(t*2) * 1.0
end)
