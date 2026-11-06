-- Capture + PostProcessing: exemplos de uso no Lua Studio
Graphics.PostProcessing.Set({
    Exposure = 0.25,
    Contrast = 1.08,
    Saturation = 1.10,
    Temperature = 0.12,
    Tint = 0.0,
    Highlights = 0.05,
    Shadows = 0.10
})

-- Foto PNG do Stage (sem capturar as barras do editor)
Capture.Screenshot({
    Filename = "minha_foto.png",
    Format = "PNG",
    Quality = 100
})

-- Gravar gameplay AVI/MJPEG; sem FFmpeg ou OpenCV
Capture.Recording.Start({
    Filename = "gameplay.avi",
    FPS = 30,
    Quality = 85
})

-- ... gameplay ...

local gravacao = Capture.Recording.Stop()
if gravacao then
    app.log("Video:", gravacao.Path, "frames:", gravacao.Frames)
end

-- Sessao de foto: salva e restaura os parametros de calibracao ao sair.
Capture.PhotoMode.Enable({FreezeGame = true})
Capture.PhotoMode.SetPostProcessing({
    Exposure = 0.8,
    Saturation = 1.2,
    Contrast = 1.1
})
-- Capture.PhotoMode.Disable() quando o jogador sair do modo foto
