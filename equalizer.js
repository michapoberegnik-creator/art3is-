const BAND_CONFIG = [
  { label: "31", frequency: 31, type: "lowshelf", gain: 0 },
  { label: "62", frequency: 62, type: "peaking", gain: 0 },
  { label: "125", frequency: 125, type: "peaking", gain: 0 },
  { label: "250", frequency: 250, type: "peaking", gain: 0 },
  { label: "500", frequency: 500, type: "peaking", gain: 0 },
  { label: "1k", frequency: 1000, type: "peaking", gain: 0 },
  { label: "2k", frequency: 2000, type: "peaking", gain: 0 },
  { label: "4k", frequency: 4000, type: "peaking", gain: 0 },
  { label: "8k", frequency: 8000, type: "peaking", gain: 0 },
  { label: "16k", frequency: 16000, type: "highshelf", gain: 0 },
];

const PRESETS = {
  Flat: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  Rock: [4, 3, 2, 1, -1, -1, 1, 2, 3, 4],
  Club: [5, 4, 2, 0, -1, -1, 1, 2, 4, 5],
  Studio: [1, 1, 0, 0, 1, 2, 2, 1, 1, 0],
  BassBoost: [6, 5, 4, 2, 0, -1, -2, -2, -1, 0],
  Vocal: [-2, -1, 0, 2, 4, 5, 4, 2, 1, 0],
};

class JavaScriptEqualizer {
  constructor({ audio, controlsRoot, presetSelect, resetButton, fileInput, status, visualizer }) {
    this.audio = audio;
    this.controlsRoot = controlsRoot;
    this.presetSelect = presetSelect;
    this.resetButton = resetButton;
    this.fileInput = fileInput;
    this.status = status;
    this.visualizer = visualizer;

    this.audioContext = null;
    this.sourceNode = null;
    this.analyser = null;
    this.filters = [];
    this.sliders = [];
    this.animationFrame = null;
  }

  init() {
    this.renderPresetOptions();
    this.renderControls();
    this.presetSelect.addEventListener("change", () => this.applyPreset(this.presetSelect.value));
    this.resetButton.addEventListener("click", () => this.applyPreset("Flat"));
    this.fileInput.addEventListener("change", (event) => this.loadFile(event));
    this.audio.addEventListener("play", async () => {
      await this.ensureAudioGraph();
      this.drawVisualizer();
    });
    this.audio.addEventListener("pause", () => this.stopVisualizer());
    this.audio.addEventListener("ended", () => this.stopVisualizer());
    this.setStatus("Load an audio file to start.");
  }

  renderPresetOptions() {
    Object.keys(PRESETS).forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      this.presetSelect.appendChild(option);
    });
    this.presetSelect.value = "Flat";
  }

  renderControls() {
    this.controlsRoot.innerHTML = "";
    BAND_CONFIG.forEach((band, index) => {
      const bandWrap = document.createElement("label");
      bandWrap.className = "band";

      const title = document.createElement("span");
      title.className = "band-label";
      title.textContent = band.label;

      const slider = document.createElement("input");
      slider.type = "range";
      slider.min = "-12";
      slider.max = "12";
      slider.step = "1";
      slider.value = String(band.gain);
      slider.className = "band-slider";
      slider.addEventListener("input", async () => {
        await this.ensureAudioGraph();
        this.filters[index].gain.value = Number(slider.value);
        this.presetSelect.value = "";
        value.textContent = `${slider.value} dB`;
      });

      const value = document.createElement("span");
      value.className = "band-value";
      value.textContent = `${band.gain} dB`;

      bandWrap.appendChild(title);
      bandWrap.appendChild(slider);
      bandWrap.appendChild(value);
      this.controlsRoot.appendChild(bandWrap);
      this.sliders.push(slider);
    });
  }

  async ensureAudioGraph() {
    if (this.audioContext) {
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }
      return;
    }

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    this.audioContext = new AudioContextClass();
    this.sourceNode = this.audioContext.createMediaElementSource(this.audio);
    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = 256;

    let previous = this.sourceNode;
    this.filters = BAND_CONFIG.map((band) => {
      const filter = this.audioContext.createBiquadFilter();
      filter.type = band.type;
      filter.frequency.value = band.frequency;
      filter.Q.value = 1;
      filter.gain.value = band.gain;
      previous.connect(filter);
      previous = filter;
      return filter;
    });

    previous.connect(this.analyser);
    this.analyser.connect(this.audioContext.destination);
  }

  applyPreset(name) {
    const values = PRESETS[name];
    if (!values) {
      return;
    }
    this.sliders.forEach((slider, index) => {
      slider.value = String(values[index]);
      const bandValue = slider.parentElement.querySelector(".band-value");
      if (bandValue) {
        bandValue.textContent = `${values[index]} dB`;
      }
      if (this.filters[index]) {
        this.filters[index].gain.value = values[index];
      }
    });
    this.setStatus(`Preset: ${name}`);
  }

  loadFile(event) {
    const [file] = event.target.files || [];
    if (!file) {
      return;
    }
    const fileUrl = URL.createObjectURL(file);
    this.audio.src = fileUrl;
    this.audio.load();
    this.setStatus(`Loaded: ${file.name}`);
  }

  drawVisualizer() {
    if (!this.analyser || !this.visualizer) {
      return;
    }
    const context = this.visualizer.getContext("2d");
    const { width, height } = this.visualizer;
    const buffer = new Uint8Array(this.analyser.frequencyBinCount);

    const paint = () => {
      this.analyser.getByteFrequencyData(buffer);
      context.clearRect(0, 0, width, height);
      context.fillStyle = "#0d141d";
      context.fillRect(0, 0, width, height);

      const barWidth = width / buffer.length;
      buffer.forEach((value, index) => {
        const scaled = (value / 255) * height;
        context.fillStyle = `hsl(${200 + index * 1.2}, 90%, ${40 + value / 8}%)`;
        context.fillRect(index * barWidth, height - scaled, Math.max(barWidth - 1, 1), scaled);
      });

      if (!this.audio.paused) {
        this.animationFrame = requestAnimationFrame(paint);
      }
    };

    this.stopVisualizer();
    paint();
  }

  stopVisualizer() {
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
  }

  setStatus(message) {
    this.status.textContent = message;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const equalizer = new JavaScriptEqualizer({
    audio: document.getElementById("audio-player"),
    controlsRoot: document.getElementById("eq-controls"),
    presetSelect: document.getElementById("preset-select"),
    resetButton: document.getElementById("reset-button"),
    fileInput: document.getElementById("file-input"),
    status: document.getElementById("status"),
    visualizer: document.getElementById("visualizer"),
  });
  equalizer.init();
});
