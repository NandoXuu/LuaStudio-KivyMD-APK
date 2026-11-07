-- 37: TESTE GRAFICO DE COLOR CALIBRATION - Android / SDL
-- Copie a imagem de referencia para assets/4k.png antes de executar.
-- A imagem fica atras do painel para comparar os ajustes visualmente.
-- Controles por toque: sliders de brilho, contraste, saturacao, realces,
-- sombras e ganho RGB. Presets e Reset tambem funcionam sem teclado.

app.background("#080a12")

local CC = Graphics.ColorCalibration
CC.Enabled = true
CC.PlayerSettingsEnabled = true
CC.PlayerControls = {
    Brightness = true,
    Contrast = true,
    Saturation = true,
    Highlights = true,
    Shadows = true,
    RGBGain = true,
    BlackPoint = false,
    WhitePoint = false,
    RGBOffset = false,
}

-- Base neutra do desenvolvedor; os sliders alteram apenas ajustes do jogador.
CC.BlackPoint = 0.0
CC.WhitePoint = 1.0
CC.Brightness = 0.0
CC.Contrast = 1.0
CC.Saturation = 1.0
CC.Highlights = 0.0
CC.Shadows = 0.0
CC.RGB.Gain = { R = 1.0, G = 1.0, B = 1.0 }
CC.RGB.Offset = { R = 0.0, G = 0.0, B = 0.0 }
CC.Player.Reset()

-- Canvas logico de referencia 1280x720. SDL/engine faz o scaling da UI.
create.image.Imagem4K = {
    Source = "assets/4k.png",
    Position = {0, 0},
    Size = {1280, 720},
    RenderLayer = 0,
}

-- Painel de leitura. Opacity e intencional: imagem continua visivel por tras.
create.frame.Painel = {
    Position = {0, 470}, Size = {1280, 250},
    Color = "#080b16", Opacity = 0.92, Radius = 0,
    RenderLayer = 10,
}
create.frame.Linha = {
    Position = {0, 468}, Size = {1280, 3},
    Color = "#39eaff", Radius = 0, RenderLayer = 11,
}

create.label.Titulo = {
    Text = "L U A S T U D I O   /   COLOR CALIBRATION",
    Position = {24, 478}, Size = {720, 28}, FontSize = 21,
    TextColor = "#39eaff", RenderLayer = 12,
}
create.label.Status = {
    Text = "Preparando calibracao...",
    Position = {760, 480}, Size = {490, 26}, FontSize = 14,
    TextColor = "#ffffff", RenderLayer = 12,
}

local values = {
    brightness = 0.0,
    contrast = 1.0,
    saturation = 1.0,
    highlights = 0.0,
    shadows = 0.0,
    r = 1.0, g = 1.0, b = 1.0,
}

local function updateStatus()
    local s = CC.GetStatus()
    local mode = tostring(s.Output or "SDR")
    app.find("Status").Text = string.format(
        "%s | ativo: %s | brilho: %.2f EV | contraste: %.2f",
        mode, tostring(s.Active), values.brightness, values.contrast)
end

local function applyValues()
    CC.Player.Brightness = values.brightness
    CC.Player.Contrast = values.contrast
    CC.Player.Saturation = values.saturation
    CC.Player.Highlights = values.highlights
    CC.Player.Shadows = values.shadows
    CC.Player.RGB.Gain = { R = values.r, G = values.g, B = values.b }
    updateStatus()
end

local function resetValues()
    values.brightness = 0.0
    values.contrast = 1.0
    values.saturation = 1.0
    values.highlights = 0.0
    values.shadows = 0.0
    values.r, values.g, values.b = 1.0, 1.0, 1.0
    CC.Player.Reset()
    app.find("Brilho").Value = values.brightness
    app.find("Contraste").Value = values.contrast
    app.find("Saturacao").Value = values.saturation
    app.find("Realces").Value = values.highlights
    app.find("Sombras").Value = values.shadows
    app.find("GanhoR").Value = values.r
    app.find("GanhoG").Value = values.g
    app.find("GanhoB").Value = values.b
    applyValues()
end

local function preset(kind)
    if kind == "neutro" then
        resetValues()
    elseif kind == "quente" then
        values.brightness, values.contrast, values.saturation = 0.05, 1.05, 1.05
        values.highlights, values.shadows = 0.10, 0.05
        values.r, values.g, values.b = 1.12, 1.0, 0.88
    elseif kind == "frio" then
        values.brightness, values.contrast, values.saturation = 0.0, 1.08, 0.95
        values.highlights, values.shadows = 0.0, 0.10
        values.r, values.g, values.b = 0.90, 1.0, 1.12
    elseif kind == "cinema" then
        values.brightness, values.contrast, values.saturation = -0.10, 1.12, 0.88
        values.highlights, values.shadows = -0.15, 0.10
        values.r, values.g, values.b = 1.03, 1.0, 0.96
    end
    app.find("Brilho").Value = values.brightness
    app.find("Contraste").Value = values.contrast
    app.find("Saturacao").Value = values.saturation
    app.find("Realces").Value = values.highlights
    app.find("Sombras").Value = values.shadows
    app.find("GanhoR").Value = values.r
    app.find("GanhoG").Value = values.g
    app.find("GanhoB").Value = values.b
    applyValues()
end

local function label(name, text, x, y, width)
    create.label[name] = {
        Text = text, Position = {x, y}, Size = {width, 20},
        FontSize = 13, TextColor = "#dbe6ff", RenderLayer = 12,
    }
end

local function slider(name, text, x, y, width, minv, maxv, value, callback)
    label(name .. "Label", text, x, y, width)
    create.slider[name] = {
        Position = {x, y + 20}, Size = {width, 22},
        Min = minv, Max = maxv, Value = value,
        Color = "#26334b", RenderLayer = 13,
        OnChange = function(self, v)
            callback(v)
            applyValues()
        end,
    }
end

-- Duas linhas de controles, adequadas a touch no SDL Android.
slider("Brilho", "BRILHO / EV", 24, 510, 270, -1.5, 1.5, values.brightness,
    function(v) values.brightness = v end)
slider("Contraste", "CONTRASTE", 318, 510, 270, 0.7, 1.4, values.contrast,
    function(v) values.contrast = v end)
slider("Saturacao", "SATURACAO", 612, 510, 270, 0.5, 1.5, values.saturation,
    function(v) values.saturation = v end)
slider("Realces", "REALCES / HIGHLIGHTS", 906, 510, 350, -0.5, 0.5, values.highlights,
    function(v) values.highlights = v end)

slider("Sombras", "SOMBRAS / SHADOWS", 24, 574, 270, -0.5, 0.5, values.shadows,
    function(v) values.shadows = v end)
slider("GanhoR", "GANHO VERMELHO", 318, 574, 270, 0.8, 1.25, values.r,
    function(v) values.r = v end)
slider("GanhoG", "GANHO VERDE", 612, 574, 270, 0.8, 1.25, values.g,
    function(v) values.g = v end)
slider("GanhoB", "GANHO AZUL", 906, 574, 350, 0.8, 1.25, values.b,
    function(v) values.b = v end)

create.button.Neutro = {
    Text = "NEUTRO / RESET", Position = {24, 648}, Size = {220, 48},
    Color = "#25334b", Radius = 8, RenderLayer = 14,
    OnClick = function() preset("neutro") end,
}
create.button.Quente = {
    Text = "QUENTE", Position = {258, 648}, Size = {170, 48},
    Color = "#8d4b35", Radius = 8, RenderLayer = 14,
    OnClick = function() preset("quente") end,
}
create.button.Frio = {
    Text = "FRIO", Position = {442, 648}, Size = {170, 48},
    Color = "#285e91", Radius = 8, RenderLayer = 14,
    OnClick = function() preset("frio") end,
}
create.button.Cinema = {
    Text = "CINEMA", Position = {626, 648}, Size = {170, 48},
    Color = "#55406e", Radius = 8, RenderLayer = 14,
    OnClick = function() preset("cinema") end,
}
create.label.Ajuda = {
    Text = "Toque nos sliders para comparar a imagem. Ganho RGB altera cada canal globalmente.",
    Position = {818, 650}, Size = {438, 42}, FontSize = 13,
    TextColor = "#b8c7e8", RenderLayer = 14,
}

-- Verifica se a imagem de referencia foi encontrada, sem interromper o teste.
local imageExists = fs.exists("assets/4k.png")
if not imageExists then
    app.find("Status").Text = "FALTA assets/4k.png | copie a imagem 4K para a pasta assets"
    print("[ColorCalibration SDL] Imagem ausente: assets/4k.png")
else
    updateStatus()
end

print("[ColorCalibration SDL] Teste pronto. Imagem encontrada: " .. tostring(imageExists))
