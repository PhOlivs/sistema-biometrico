/**
 * BIOAUTH - camera.js
 * --------------------------------------------------------------
 * Responsável pela AQUISIÇÃO DE IMAGEM (etapa 1 do processamento
 * digital de imagem): solicita acesso à webcam via getUserMedia()
 * e exibe o vídeo ao vivo na tela de autenticação.
 *
 * Este módulo NÃO realiza detecção facial, extração de
 * características, reconhecimento nem autorização. Essas
 * responsabilidades pertencem a módulos futuros (biometric/,
 * services/), que receberão apenas um frame já capturado por aqui.
 *
 * Fluxo desta fase:
 *   webcam → getUserMedia() → <video> exibido no navegador
 *
 * Fluxo que será adicionado nas próximas fases:
 *   <video> → captura de um frame (canvas) → envio ao Flask →
 *   camera_service.py → face_detector.py → ...
 */

(function () {
    "use strict";

    const video = document.getElementById("camera-feed");
    const placeholder = document.getElementById("camera-placeholder");
    const statusDot = document.getElementById("camera-status-dot");
    const footerText = document.getElementById("camera-footer-text");

    // Se a página atual não tiver os elementos de câmera (ex.: index.html),
    // este script simplesmente não faz nada.
    if (!video || !placeholder || !statusDot || !footerText) {
        return;
    }

    const placeholderTitle = placeholder.querySelector(".camera-status-text");
    const placeholderHint = placeholder.querySelector(".camera-status-hint");

    /**
     * Atualiza o indicador de status no rodapé do card da câmera.
     * O estado é comunicado por texto E cor (não depende só da cor).
     */
    function setFooterStatus(state, message) {
        statusDot.className = "status-dot status-dot--" + state;
        footerText.textContent = message;
    }

    /**
     * Exibe o placeholder (câmera inativa ou com erro) e esconde o vídeo.
     */
    function showPlaceholder(title, hint) {
        video.hidden = true;
        placeholder.hidden = false;
        placeholderTitle.textContent = title;
        placeholderHint.textContent = hint;
    }

    /**
     * Exibe o vídeo ao vivo e esconde o placeholder.
     */
    function showVideo() {
        placeholder.hidden = true;
        video.hidden = false;
    }

    /**
     * Traduz os erros do getUserMedia() para mensagens amigáveis,
     * conforme os cenários previstos no projeto (câmera não encontrada,
     * câmera ocupada, permissão negada).
     */
    function handleCameraError(error) {
        console.error("Erro ao acessar a câmera:", error);

        switch (error.name) {
            case "NotFoundError":
            case "OverconstrainedError":
                showPlaceholder(
                    "Câmera não encontrada",
                    "Verifique se há uma webcam conectada ao dispositivo."
                );
                setFooterStatus("error", "Câmera não encontrada");
                break;

            case "NotReadableError":
            case "TrackStartError":
                showPlaceholder(
                    "Câmera ocupada",
                    "A câmera pode estar sendo usada por outro aplicativo."
                );
                setFooterStatus("error", "Câmera ocupada");
                break;

            case "NotAllowedError":
            case "PermissionDeniedError":
                showPlaceholder(
                    "Permissão de câmera negada",
                    "Autorize o acesso à câmera nas configurações do navegador e recarregue a página."
                );
                setFooterStatus("error", "Permissão negada");
                break;

            default:
                showPlaceholder(
                    "Erro ao acessar a câmera",
                    "Ocorreu um erro inesperado ao iniciar o sensor de imagem."
                );
                setFooterStatus("error", "Erro desconhecido");
        }
    }

    /**
     * Solicita acesso à webcam e conecta o stream ao elemento <video>.
     */
    async function startCamera() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showPlaceholder(
                "Câmera não suportada",
                "Este navegador não oferece suporte à captura de vídeo."
            );
            setFooterStatus("error", "Câmera não suportada");
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480 },
                audio: false,
            });

            video.srcObject = stream;
            showVideo();
            setFooterStatus("ok", "Câmera ativa");
        } catch (error) {
            handleCameraError(error);
        }
    }

    startCamera();
})();
