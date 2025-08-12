class AudioControls {
    constructor(audioSystem) {
        this.audioSystem = audioSystem;
        this.container = null;
        this.volumeSlider = null;
        this.muteButton = null;
        this.isVisible = true;
    }

    init(containerId = 'audio-controls') {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            this.createContainer(containerId);
        }
        
        this.render();
        this.attachEventListeners();
        this.audioSystem.init();
    }

    createContainer(id) {
        this.container = document.createElement('div');
        this.container.id = id;
        this.container.className = 'audio-controls';
        document.body.appendChild(this.container);
    }

    render() {
        this.container.innerHTML = `
            <div class="audio-controls-wrapper">
                <div class="audio-control-group">
                    <button id="mute-toggle" class="retro-button" aria-label="Toggle mute">
                        <span class="mute-icon">${this.audioSystem.isMuted ? '🔇' : '🔊'}</span>
                    </button>
                    <div class="volume-control">
                        <label for="volume-slider" class="retro-label">VOL</label>
                        <input 
                            type="range" 
                            id="volume-slider" 
                            class="retro-slider"
                            min="0" 
                            max="100" 
                            value="${this.audioSystem.volume * 100}"
                            ${this.audioSystem.isMuted ? 'disabled' : ''}
                        >
                        <span class="volume-value">${Math.round(this.audioSystem.volume * 100)}%</span>
                    </div>
                </div>
                <div class="audio-shortcuts">
                    <span class="shortcut-hint">M: Mute</span>
                    <span class="shortcut-hint">+/-: Volume</span>
                </div>
            </div>
        `;
        
        this.volumeSlider = this.container.querySelector('#volume-slider');
        this.muteButton = this.container.querySelector('#mute-toggle');
        
        this.applyStyles();
    }

    applyStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .audio-controls {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: rgba(0, 0, 0, 0.9);
                border: 2px solid #00ff00;
                border-radius: 8px;
                padding: 15px;
                font-family: 'Courier New', monospace;
                color: #ffffff;
                z-index: 1000;
                box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
            }
            
            .audio-controls-wrapper {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            
            .audio-control-group {
                display: flex;
                align-items: center;
                gap: 15px;
            }
            
            .retro-button {
                background: #000000;
                border: 2px solid #00ff00;
                color: #00ff00;
                padding: 8px 12px;
                font-family: 'Courier New', monospace;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.2s;
                border-radius: 4px;
            }
            
            .retro-button:hover {
                background: #00ff00;
                color: #000000;
                box-shadow: 0 0 10px #00ff00;
            }
            
            .retro-button:active {
                transform: scale(0.95);
            }
            
            .retro-button.muted {
                border-color: #ff0000;
                color: #ff0000;
            }
            
            .retro-button.muted:hover {
                background: #ff0000;
                color: #000000;
                box-shadow: 0 0 10px #ff0000;
            }
            
            .mute-icon {
                font-size: 20px;
                display: inline-block;
            }
            
            .volume-control {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .retro-label {
                color: #00ff00;
                font-size: 14px;
                font-weight: bold;
                text-shadow: 0 0 5px #00ff00;
            }
            
            .retro-slider {
                width: 100px;
                height: 8px;
                background: #333333;
                outline: none;
                border: 1px solid #00ff00;
                border-radius: 4px;
                cursor: pointer;
            }
            
            .retro-slider::-webkit-slider-thumb {
                -webkit-appearance: none;
                appearance: none;
                width: 16px;
                height: 16px;
                background: #00ff00;
                border: 2px solid #000000;
                border-radius: 50%;
                cursor: pointer;
                box-shadow: 0 0 5px #00ff00;
            }
            
            .retro-slider::-moz-range-thumb {
                width: 16px;
                height: 16px;
                background: #00ff00;
                border: 2px solid #000000;
                border-radius: 50%;
                cursor: pointer;
                box-shadow: 0 0 5px #00ff00;
            }
            
            .retro-slider:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .volume-value {
                color: #00ff00;
                font-size: 14px;
                min-width: 40px;
                text-align: right;
                text-shadow: 0 0 5px #00ff00;
            }
            
            .audio-shortcuts {
                display: flex;
                gap: 15px;
                justify-content: center;
                margin-top: 5px;
            }
            
            .shortcut-hint {
                color: #888888;
                font-size: 11px;
                text-transform: uppercase;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }
            
            .audio-controls.pulse {
                animation: pulse 1s ease-in-out;
            }
        `;
        
        if (!document.querySelector('#audio-controls-styles')) {
            style.id = 'audio-controls-styles';
            document.head.appendChild(style);
        }
    }

    attachEventListeners() {
        this.muteButton.addEventListener('click', () => {
            this.toggleMute();
        });
        
        this.volumeSlider.addEventListener('input', (e) => {
            this.setVolume(e.target.value / 100);
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key.toLowerCase() === 'm') {
                this.toggleMute();
            } else if (e.key === '+' || e.key === '=') {
                this.adjustVolume(0.1);
            } else if (e.key === '-' || e.key === '_') {
                this.adjustVolume(-0.1);
            }
        });
    }

    toggleMute() {
        const isMuted = this.audioSystem.toggleMute();
        this.updateMuteButton(isMuted);
        this.volumeSlider.disabled = isMuted;
        
        this.container.classList.add('pulse');
        setTimeout(() => {
            this.container.classList.remove('pulse');
        }, 1000);
    }

    updateMuteButton(isMuted) {
        this.muteButton.classList.toggle('muted', isMuted);
        this.muteButton.querySelector('.mute-icon').textContent = isMuted ? '🔇' : '🔊';
    }

    setVolume(volume) {
        this.audioSystem.setVolume(volume);
        this.volumeSlider.value = volume * 100;
        this.container.querySelector('.volume-value').textContent = `${Math.round(volume * 100)}%`;
    }

    adjustVolume(delta) {
        const currentVolume = this.audioSystem.volume;
        const newVolume = Math.max(0, Math.min(1, currentVolume + delta));
        this.setVolume(newVolume);
    }

    show() {
        this.isVisible = true;
        this.container.style.display = 'block';
    }

    hide() {
        this.isVisible = false;
        this.container.style.display = 'none';
    }

    toggle() {
        if (this.isVisible) {
            this.hide();
        } else {
            this.show();
        }
    }

    testSounds() {
        console.log('Testing audio system sounds...');
        
        setTimeout(() => this.audioSystem.playIntro(), 100);
        setTimeout(() => this.audioSystem.playWakka(), 2000);
        setTimeout(() => this.audioSystem.playPowerPellet(), 2500);
        setTimeout(() => this.audioSystem.playFruitCollected(), 3000);
        setTimeout(() => this.audioSystem.playGhostEaten(), 3500);
        setTimeout(() => this.audioSystem.playLevelComplete(), 4000);
        setTimeout(() => {
            this.audioSystem.startSiren();
            setTimeout(() => this.audioSystem.stopSiren(), 2000);
        }, 5000);
        setTimeout(() => this.audioSystem.playDeath(), 8000);
    }
}

export default AudioControls;