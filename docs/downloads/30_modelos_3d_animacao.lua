app.background("#0b1020")
Env3D.set({ Ambient = 0.45, FogColor = "#0b1020", FogStart = 12, FogEnd = 30 })
create.camera.Main = { Position = {0, 1.6, -6}, Target = {0, 1, 0}, FOV = 60 }
create.part.Chao = { Shape = "plane", Position = {0, 0, 0}, Size = {12, 1, 12}, Color = "#22314d" }
create.model.Robo = { Source = "assets3d/robo_animado.glb", Position = {-1.6, 0, 0} }
create.model.Caixa = { Source = "assets3d/caixa_textura.obj", Position = {1.6, 0.6, 0}, Scale = {0.6, 0.6, 0.6} }
create.label.HUD = { Text = "Modelos 3D", Position = {16, 16}, Size = {300, 36}, FontSize = 22, TextColor = "white" }

Animation.load("assets3d/robo_clips.lsa")
local robo = create.model.Robo
local caixa = create.model.Caixa
local nomes = { "Idle", "Walk", "Acenar" }
local atual = 1
local tempo = 0

robo:Play("Idle", { Loop = true })

onUpdate(function(dt, t)
  tempo = tempo + dt
  if tempo >= 3 then
    tempo = 0
    atual = (atual % #nomes) + 1
    robo:Play(nomes[atual], { Loop = true, Blend = 0.4 })
  end
  caixa.Rotation3 = vec3(0, t * 40, 0)
  app.find("HUD").Text = "Clipe: " .. nomes[atual] .. "  (" .. string.format("%.1f", robo:GetTime()) .. "s)"
end)
