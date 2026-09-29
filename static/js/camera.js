"use strict";

(() => {
  const workspace = document.getElementById("biometric-capture");
  if (!workspace) return;

  const video = document.getElementById("camera-feed");
  const placeholder = document.getElementById("camera-placeholder");
  const statusText = document.getElementById("camera-status-text");
  const statusHint = document.getElementById("camera-status-hint");
  const button = document.getElementById("capture-button");
  const feedback = document.getElementById("camera-feedback");
  const instruction = document.getElementById("camera-instruction");
  const progress = document.getElementById("capture-progress");
  const stepLabel = document.getElementById("capture-step");
  const angleLabel = document.getElementById("capture-angle");
  const progressFill = document.getElementById("progress-fill");
  const mode = workspace.dataset.mode;
  const angles = [
    { key: "FRONT", title: "frontal", instruction: "Olhe diretamente para a câmera." },
    { key: "RIGHT", title: "lateral direita", instruction: "Vire lentamente o rosto para a direita." },
    { key: "LEFT", title: "lateral esquerda", instruction: "Vire lentamente o rosto para a esquerda." },
  ];
  const frames = {};
  let angleIndex = 0;
  let stream;
  let busy = false;

  function showError(message) {
    feedback.textContent = message;
    feedback.classList.add("is-error");
  }

  function updateProgress() {
    const angle = angles[angleIndex];
    stepLabel.textContent = `ETAPA ${angleIndex + 1} DE ${angles.length}`;
    angleLabel.textContent = angle.title.toLocaleUpperCase("pt-BR");
    instruction.textContent = angle.instruction;
    button.textContent = `Capturar rosto ${angle.title}`;
    progressFill.style.width = `${(angleIndex / angles.length) * 100}%`;
  }

  function captureFrame() {
    if (!video.videoWidth || !video.videoHeight) {
      throw new Error("A câmera ainda está inicializando. Aguarde um instante.");
    }
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 1280 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext("2d", { alpha: false });
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.88);
  }

  async function sendCapture(url, payload) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Não foi possível concluir a autenticação.");
    window.location.assign(result.redirect);
  }

  async function capture() {
    if (busy || !workspace.dataset.ready || !stream) return;
    busy = true;
    button.disabled = true;
    feedback.classList.remove("is-error");
    feedback.textContent = "Processando captura…";
    try {
      const image = captureFrame();
      if (mode === "verify") {
        await sendCapture(workspace.dataset.verifyUrl, { image });
        return;
      }
      frames[angles[angleIndex].key] = image;
      angleIndex += 1;
      if (angleIndex < angles.length) {
        updateProgress();
        feedback.textContent = "Captura recebida. Prepare a próxima posição.";
      } else {
        button.textContent = "Validando as três capturas…";
        const url = mode === "setup" ? workspace.dataset.setupUrl : workspace.dataset.enrollUrl;
        await sendCapture(url, { images: frames });
        return;
      }
    } catch (error) {
      console.error("Falha no fluxo biométrico:", error);
      showError(error.message || "Falha ao processar a captura.");
    } finally {
      busy = false;
      button.disabled = !stream || workspace.dataset.ready !== "true";
      if (mode !== "verify" && angleIndex < angles.length && !button.disabled) {
        updateProgress();
      }
    }
  }

  function showCameraError(error) {
    console.error("Não foi possível acessar a câmera:", error);
    const messages = {
      NotFoundError: ["Câmera não encontrada", "Conecte uma câmera compatível e recarregue a página."],
      NotAllowedError: ["Permissão negada", "Permita o uso da câmera nas configurações do navegador."],
      NotReadableError: ["Câmera indisponível", "A câmera pode estar sendo usada por outro aplicativo."],
      SecurityError: ["Conexão não segura", "A câmera requer HTTPS ou acesso local em localhost."],
    };
    const [title, hint] = messages[error.name] || [
      "Falha ao iniciar a câmera",
      "Verifique as permissões e tente novamente.",
    ];
    statusText.textContent = title;
    statusHint.textContent = hint;
    button.disabled = true;
  }

  async function startCamera() {
    if (workspace.dataset.ready !== "true") {
      statusText.textContent = "Biometria não configurada";
      statusHint.textContent = "Os modelos faciais precisam estar instalados no servidor.";
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      showCameraError({ name: "NotFoundError" });
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      placeholder.hidden = true;
      button.disabled = false;
      statusText.textContent = "Câmera ativa";
      statusHint.textContent = "Mantenha o rosto centralizado e siga as instruções.";
      if (mode !== "verify") updateProgress();
    } catch (error) {
      showCameraError(error);
    }
  }

  button.addEventListener("click", capture);
  window.addEventListener("pagehide", () => stream?.getTracks().forEach((track) => track.stop()), { once: true });
  startCamera();
})();
