local function montarChao(cor)
  create.part.Chao = { Shape = "plane", Position = {0, 0, 0}, Size = {20, 1, 20}, Color = cor }
  create.camera.Main = { Position = {0, 4, -12}, Target = {0, 0.5, 0}, FOV = 62 }
  create.model.Robo = { Source = "assets3d/robo_animado.glb", Position = {0, 0, 0} }
  create.model.Robo:Play("Idle", { Loop = true })
end

local function cicloAte(proxima)
  local tempo = 0
  onUpdate(function(dt)
    tempo = tempo + dt
    if tempo >= 5 then
      Scenes.load(proxima, 0.8)
    end
  end)
end

Scenes.register("Dia", function()
  app.background("#8fc8f0")
  Env3D.set({ FogColor = "#b9dcf5", FogStart = 10, FogEnd = 40, Ambient = 0.6,
              SunDirection = {0.2, -1, 0.3}, SunIntensity = 0.9, SunColor = "#fff6dc" })
  montarChao("#5a9e4b")
  create.part.Pilar = { Shape = "cylinder", Position = {5, 1.5, 4}, Size = {0.6, 1.5, 0.6}, Color = "#c9a66b" }
  create.label.Titulo = { Text = "Cenário: Dia", Position = {16, 16}, Size = {300, 36}, FontSize = 22, TextColor = "#1b2b1b" }
  cicloAte("Noite")
end)

Scenes.register("Noite", function()
  app.background("#050814")
  Env3D.set({ FogColor = "#0a1024", FogStart = 4, FogEnd = 18, Ambient = 0.15,
              SunDirection = {-0.4, -0.6, 0.6}, SunIntensity = 0.35, SunColor = "#8ea6ff" })
  montarChao("#1a2a3a")
  create.part.Pilar = { Shape = "cylinder", Position = {5, 1.5, 4}, Size = {0.6, 1.5, 0.6}, Color = "#3b4a6b" }
  create.label.Titulo = { Text = "Cenário: Noite", Position = {16, 16}, Size = {300, 36}, FontSize = 22, TextColor = "white" }
  cicloAte("Dia")
end)

Scenes.load("Dia")
