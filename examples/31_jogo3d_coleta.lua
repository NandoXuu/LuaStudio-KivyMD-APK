app.background("#070b16")
Env3D.set({ Ambient = 0.4, FogColor = "#070b16", FogStart = 9, FogEnd = 24, SunDirection = {0.3, -1, 0.4} })
create.camera.Main = { Position = {0, 5, -9}, Target = {0, 0.5, 0}, FOV = 58 }
create.part.Chao = { Shape = "plane", Position = {0, 0, 0}, Size = {14, 1, 14}, Color = "#1c2a44" }
create.model.Jogador = { Source = "assets3d/robo_animado.glb", Position = {0, 0, 0} }
create.label.Placar = { Text = "", Position = {16, 16}, Size = {320, 36}, FontSize = 22, TextColor = "white" }

local jogador = create.model.Jogador
local px, pz = 0, 0
local vel = 4.5
local pontos = 0
local restante = 30
local reinicio = 0
local moedas = {}
local andando = false
local contador = 0

local function spawnMoedas()
  for i = 1, 8 do
    local x = math.random(-6, 6)
    local z = math.random(-6, 6)
    local nome = "Moeda" .. i
    create.part[nome] = { Shape = "cylinder", Position = {x, 0.6, z}, Size = {0.35, 0.08, 0.35}, Color = "yellow" }
    moedas[#moedas + 1] = { nome = nome, x = x, z = z }
  end
end

local function limpar()
  for _, m in ipairs(moedas) do
    app.destroy(m.nome)
  end
  moedas = {}
end

local function resetar()
  limpar()
  pontos = 0
  restante = 30
  px, pz = 0, 0
  jogador.Position = vec3(0, 0, 0)
  spawnMoedas()
end

resetar()
jogador:Play("Idle", { Loop = true })

onUpdate(function(dt, t)
  if reinicio > 0 then
    reinicio = reinicio - dt
    app.find("Placar").Text = "Fim! Moedas: " .. pontos .. "  (novo jogo em " .. math.ceil(reinicio) .. "s)"
    if reinicio <= 0 then resetar() end
    return
  end

  restante = restante - dt
  local dx, dz = 0, 0
  if input.keyboard.isDown("LEFT") then dx = dx - 1 end
  if input.keyboard.isDown("RIGHT") then dx = dx + 1 end
  if input.keyboard.isDown("UP") then dz = dz + 1 end
  if input.keyboard.isDown("DOWN") then dz = dz - 1 end

  local movendo = dx ~= 0 or dz ~= 0
  if movendo then
    local n = math.sqrt(dx * dx + dz * dz)
    px = math.max(-6.5, math.min(6.5, px + dx / n * vel * dt))
    pz = math.max(-6.5, math.min(6.5, pz + dz / n * vel * dt))
    jogador.Rotation3 = vec3(0, math.deg(math.atan(dx, dz)), 0)
  end
  jogador.Position = vec3(px, 0, pz)
  if movendo ~= andando then
    andando = movendo
    jogador:Play(andando and "Walk" or "Idle", { Loop = true, Blend = 0.25 })
  end

  local restantes = {}
  for _, m in ipairs(moedas) do
    local d = math.sqrt((m.x - px) ^ 2 + (m.z - pz) ^ 2)
    if d < 0.9 then
      app.destroy(m.nome)
      pontos = pontos + 1
    else
      restantes[#restantes + 1] = m
      app.find(m.nome).Rotation3 = vec3(90, t * 140, 0)
    end
  end
  moedas = restantes

  if restante <= 0 then
    reinicio = 3
    restante = 0
  end
  app.find("Placar").Text = "Moedas: " .. pontos .. "   Tempo: " .. math.ceil(restante)
end)
