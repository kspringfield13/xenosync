class AudioSystem {
    constructor() {
        this.audioContext = null;
        this.masterGainNode = null;
        this.sounds = {};
        this.oscillators = {};
        this.isInitialized = false;
        this.isMuted = false;
        this.volume = 0.7;
        this.sirenSpeed = 1.0;
        this.sirenInterval = null;
        this.currentMusic = null;
    }

    init() {
        if (this.isInitialized) return;
        
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.masterGainNode = this.audioContext.createGain();
            this.masterGainNode.connect(this.audioContext.destination);
            this.masterGainNode.gain.value = this.volume;
            
            this.createSounds();
            this.isInitialized = true;
        } catch (error) {
            console.error('Failed to initialize audio system:', error);
        }
    }

    createSounds() {
        this.createWakkaWakka();
        this.createGhostSiren();
        this.createPowerPelletSound();
        this.createGhostEatenSound();
        this.createDeathSound();
        this.createLevelCompleteSound();
        this.createFruitSound();
        this.createIntroMusic();
    }

    createWakkaWakka() {
        this.sounds.wakka = () => {
            if (this.isMuted) return;
            
            const oscillator = this.audioContext.createOscillator();
            const gainNode = this.audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(this.masterGainNode);
            
            oscillator.type = 'square';
            
            const now = this.audioContext.currentTime;
            oscillator.frequency.setValueAtTime(440, now);
            oscillator.frequency.exponentialRampToValueAtTime(220, now + 0.05);
            oscillator.frequency.exponentialRampToValueAtTime(110, now + 0.1);
            
            gainNode.gain.setValueAtTime(0.3, now);
            gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.1);
            
            oscillator.start(now);
            oscillator.stop(now + 0.1);
        };
    }

    createGhostSiren() {
        this.sounds.sirenStart = () => {
            if (this.isMuted || this.sirenInterval) return;
            
            let frequency = 200;
            let direction = 1;
            
            this.sirenInterval = setInterval(() => {
                if (this.oscillators.siren) {
                    this.oscillators.siren.stop();
                }
                
                const oscillator = this.audioContext.createOscillator();
                const gainNode = this.audioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(this.masterGainNode);
                
                oscillator.type = 'sawtooth';
                oscillator.frequency.value = frequency;
                gainNode.gain.value = 0.1;
                
                oscillator.start();
                this.oscillators.siren = oscillator;
                
                frequency += (20 * direction * this.sirenSpeed);
                if (frequency > 400 || frequency < 200) {
                    direction *= -1;
                }
            }, 100 / this.sirenSpeed);
        };
        
        this.sounds.sirenStop = () => {
            if (this.sirenInterval) {
                clearInterval(this.sirenInterval);
                this.sirenInterval = null;
            }
            if (this.oscillators.siren) {
                this.oscillators.siren.stop();
                this.oscillators.siren = null;
            }
        };
    }

    createPowerPelletSound() {
        this.sounds.powerPellet = () => {
            if (this.isMuted) return;
            
            const oscillator = this.audioContext.createOscillator();
            const gainNode = this.audioContext.createGain();
            const filter = this.audioContext.createBiquadFilter();
            
            oscillator.connect(filter);
            filter.connect(gainNode);
            gainNode.connect(this.masterGainNode);
            
            oscillator.type = 'square';
            filter.type = 'lowpass';
            filter.frequency.value = 1000;
            
            const now = this.audioContext.currentTime;
            
            for (let i = 0; i < 10; i++) {
                const time = now + (i * 0.05);
                oscillator.frequency.setValueAtTime(200 + (i * 50), time);
            }
            
            gainNode.gain.setValueAtTime(0.4, now);
            gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.5);
            
            oscillator.start(now);
            oscillator.stop(now + 0.5);
        };
    }

    createGhostEatenSound() {
        this.sounds.ghostEaten = () => {
            if (this.isMuted) return;
            
            const oscillator = this.audioContext.createOscillator();
            const gainNode = this.audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(this.masterGainNode);
            
            oscillator.type = 'sawtooth';
            
            const now = this.audioContext.currentTime;
            oscillator.frequency.setValueAtTime(1000, now);
            oscillator.frequency.exponentialRampToValueAtTime(100, now + 0.3);
            
            gainNode.gain.setValueAtTime(0.5, now);
            gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
            
            oscillator.start(now);
            oscillator.stop(now + 0.3);
        };
    }

    createDeathSound() {
        this.sounds.death = () => {
            if (this.isMuted) return;
            
            const oscillator1 = this.audioContext.createOscillator();
            const oscillator2 = this.audioContext.createOscillator();
            const gainNode = this.audioContext.createGain();
            
            oscillator1.connect(gainNode);
            oscillator2.connect(gainNode);
            gainNode.connect(this.masterGainNode);
            
            oscillator1.type = 'square';
            oscillator2.type = 'sawtooth';
            
            const now = this.audioContext.currentTime;
            
            oscillator1.frequency.setValueAtTime(400, now);
            oscillator1.frequency.exponentialRampToValueAtTime(50, now + 1.5);
            
            oscillator2.frequency.setValueAtTime(600, now);
            oscillator2.frequency.exponentialRampToValueAtTime(40, now + 1.5);
            
            gainNode.gain.setValueAtTime(0.4, now);
            gainNode.gain.setValueAtTime(0.4, now + 0.5);
            gainNode.gain.exponentialRampToValueAtTime(0.01, now + 1.5);
            
            oscillator1.start(now);
            oscillator1.stop(now + 1.5);
            oscillator2.start(now);
            oscillator2.stop(now + 1.5);
        };
    }

    createLevelCompleteSound() {
        this.sounds.levelComplete = () => {
            if (this.isMuted) return;
            
            const notes = [523, 659, 784, 1047, 784, 659, 523];
            const duration = 0.15;
            
            notes.forEach((freq, index) => {
                const oscillator = this.audioContext.createOscillator();
                const gainNode = this.audioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(this.masterGainNode);
                
                oscillator.type = 'sine';
                
                const startTime = this.audioContext.currentTime + (index * duration);
                oscillator.frequency.value = freq;
                
                gainNode.gain.setValueAtTime(0, startTime);
                gainNode.gain.linearRampToValueAtTime(0.3, startTime + 0.01);
                gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration);
                
                oscillator.start(startTime);
                oscillator.stop(startTime + duration);
            });
        };
    }

    createFruitSound() {
        this.sounds.fruit = () => {
            if (this.isMuted) return;
            
            const oscillator = this.audioContext.createOscillator();
            const gainNode = this.audioContext.createGain();
            const filter = this.audioContext.createBiquadFilter();
            
            oscillator.connect(filter);
            filter.connect(gainNode);
            gainNode.connect(this.masterGainNode);
            
            oscillator.type = 'sine';
            filter.type = 'bandpass';
            filter.frequency.value = 1000;
            filter.Q.value = 10;
            
            const now = this.audioContext.currentTime;
            
            oscillator.frequency.setValueAtTime(800, now);
            oscillator.frequency.exponentialRampToValueAtTime(1600, now + 0.1);
            oscillator.frequency.exponentialRampToValueAtTime(800, now + 0.2);
            
            gainNode.gain.setValueAtTime(0.5, now);
            gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
            
            oscillator.start(now);
            oscillator.stop(now + 0.3);
        };
    }

    createIntroMusic() {
        this.sounds.intro = () => {
            if (this.isMuted) return;
            
            const melody = [
                { freq: 523, duration: 0.1 },
                { freq: 523, duration: 0.1 },
                { freq: 659, duration: 0.1 },
                { freq: 784, duration: 0.1 },
                { freq: 659, duration: 0.1 },
                { freq: 523, duration: 0.2 },
                { freq: 784, duration: 0.1 },
                { freq: 784, duration: 0.1 },
                { freq: 698, duration: 0.1 },
                { freq: 659, duration: 0.1 },
                { freq: 587, duration: 0.1 },
                { freq: 523, duration: 0.3 }
            ];
            
            let currentTime = this.audioContext.currentTime;
            
            melody.forEach(note => {
                const oscillator = this.audioContext.createOscillator();
                const gainNode = this.audioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(this.masterGainNode);
                
                oscillator.type = 'square';
                oscillator.frequency.value = note.freq;
                
                gainNode.gain.setValueAtTime(0, currentTime);
                gainNode.gain.linearRampToValueAtTime(0.2, currentTime + 0.01);
                gainNode.gain.setValueAtTime(0.2, currentTime + note.duration - 0.01);
                gainNode.gain.linearRampToValueAtTime(0, currentTime + note.duration);
                
                oscillator.start(currentTime);
                oscillator.stop(currentTime + note.duration);
                
                currentTime += note.duration;
            });
        };
    }

    playWakka() {
        if (this.sounds.wakka) {
            this.sounds.wakka();
        }
    }

    startSiren() {
        if (this.sounds.sirenStart) {
            this.sounds.sirenStart();
        }
    }

    stopSiren() {
        if (this.sounds.sirenStop) {
            this.sounds.sirenStop();
        }
    }

    setSirenSpeed(speed) {
        this.sirenSpeed = Math.max(0.5, Math.min(3.0, speed));
        if (this.sirenInterval) {
            this.stopSiren();
            this.startSiren();
        }
    }

    playPowerPellet() {
        if (this.sounds.powerPellet) {
            this.sounds.powerPellet();
        }
    }

    playGhostEaten() {
        if (this.sounds.ghostEaten) {
            this.sounds.ghostEaten();
        }
    }

    playDeath() {
        this.stopSiren();
        if (this.sounds.death) {
            this.sounds.death();
        }
    }

    playLevelComplete() {
        this.stopSiren();
        if (this.sounds.levelComplete) {
            this.sounds.levelComplete();
        }
    }

    playFruitCollected() {
        if (this.sounds.fruit) {
            this.sounds.fruit();
        }
    }

    playIntro() {
        if (this.sounds.intro) {
            this.sounds.intro();
        }
    }

    setVolume(volume) {
        this.volume = Math.max(0, Math.min(1, volume));
        if (this.masterGainNode) {
            this.masterGainNode.gain.value = this.isMuted ? 0 : this.volume;
        }
    }

    mute() {
        this.isMuted = true;
        if (this.masterGainNode) {
            this.masterGainNode.gain.value = 0;
        }
    }

    unmute() {
        this.isMuted = false;
        if (this.masterGainNode) {
            this.masterGainNode.gain.value = this.volume;
        }
    }

    toggleMute() {
        if (this.isMuted) {
            this.unmute();
        } else {
            this.mute();
        }
        return this.isMuted;
    }

    cleanup() {
        this.stopSiren();
        if (this.audioContext) {
            this.audioContext.close();
        }
    }
}

export default AudioSystem;