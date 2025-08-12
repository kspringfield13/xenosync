class VisualEffects {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.particles = [];
        this.screenFlashes = [];
        this.crtEffect = true;
        this.scanlineOffset = 0;
        this.glowIntensity = 0;
        this.attractModeTimer = 0;
        this.attractModeActive = false;
        this.idleTimer = 0;
        this.idleThreshold = 30000;
        this.pixelSize = 2;
        this.retroColors = {
            red: '#FF0000',
            pink: '#FFB8FF',
            cyan: '#00FFFF',
            orange: '#FFB852',
            yellow: '#FFFF00',
            white: '#FFFFFF',
            blue: '#0000FF',
            green: '#00FF00'
        };
    }

    update(deltaTime) {
        this.updateParticles(deltaTime);
        this.updateScreenFlashes(deltaTime);
        this.updateScanlines(deltaTime);
        this.updateIdleTimer(deltaTime);
        
        if (this.attractModeActive) {
            this.updateAttractMode(deltaTime);
        }
    }

    updateParticles(deltaTime) {
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const particle = this.particles[i];
            particle.life -= deltaTime;
            
            if (particle.life <= 0) {
                this.particles.splice(i, 1);
                continue;
            }

            particle.x += particle.vx * deltaTime * 0.1;
            particle.y += particle.vy * deltaTime * 0.1;
            particle.vx *= 0.98;
            particle.vy *= 0.98;
            particle.opacity = particle.life / particle.maxLife;
            
            if (particle.type === 'dot') {
                particle.size = Math.max(1, particle.size * 0.95);
            }
        }
    }

    updateScreenFlashes(deltaTime) {
        for (let i = this.screenFlashes.length - 1; i >= 0; i--) {
            const flash = this.screenFlashes[i];
            flash.duration -= deltaTime;
            
            if (flash.duration <= 0) {
                this.screenFlashes.splice(i, 1);
            } else {
                flash.opacity = flash.duration / flash.maxDuration;
            }
        }
    }

    updateScanlines(deltaTime) {
        this.scanlineOffset += deltaTime * 0.05;
        if (this.scanlineOffset > 4) {
            this.scanlineOffset = 0;
        }
    }

    updateIdleTimer(deltaTime) {
        this.idleTimer += deltaTime;
        
        if (this.idleTimer >= this.idleThreshold && !this.attractModeActive) {
            this.startAttractMode();
        }
    }

    updateAttractMode(deltaTime) {
        this.attractModeTimer += deltaTime;
        this.glowIntensity = Math.sin(this.attractModeTimer * 0.002) * 0.5 + 0.5;
    }

    createDotParticles(x, y) {
        const particleCount = 8;
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 * i) / particleCount;
            const speed = 2 + Math.random() * 2;
            
            this.particles.push({
                type: 'dot',
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 3,
                color: this.retroColors.yellow,
                life: 500,
                maxLife: 500,
                opacity: 1
            });
        }
    }

    createPowerPelletParticles(x, y) {
        const particleCount = 16;
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 * i) / particleCount;
            const speed = 3 + Math.random() * 3;
            
            this.particles.push({
                type: 'power',
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 5,
                color: Math.random() > 0.5 ? this.retroColors.white : this.retroColors.cyan,
                life: 800,
                maxLife: 800,
                opacity: 1
            });
        }
        
        this.addScreenFlash(this.retroColors.white, 0.3, 200);
    }

    createGhostEatenParticles(x, y, points) {
        const colors = [this.retroColors.cyan, this.retroColors.white, this.retroColors.yellow];
        const particleCount = 20;
        
        for (let i = 0; i < particleCount; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 1 + Math.random() * 4;
            
            this.particles.push({
                type: 'ghost',
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 2,
                size: 4 + Math.random() * 4,
                color: colors[Math.floor(Math.random() * colors.length)],
                life: 1000,
                maxLife: 1000,
                opacity: 1
            });
        }
    }

    createDeathParticles(x, y) {
        const particleCount = 32;
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 * i) / particleCount;
            const speed = 2 + Math.random() * 3;
            
            this.particles.push({
                type: 'death',
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 3 + Math.random() * 3,
                color: this.retroColors.yellow,
                life: 1200,
                maxLife: 1200,
                opacity: 1
            });
        }
    }

    addScreenFlash(color, opacity, duration) {
        this.screenFlashes.push({
            color: color,
            opacity: opacity,
            duration: duration,
            maxDuration: duration
        });
    }

    drawParticles(ctx) {
        ctx.save();
        
        this.particles.forEach(particle => {
            ctx.globalAlpha = particle.opacity;
            ctx.fillStyle = particle.color;
            
            const x = Math.floor(particle.x / this.pixelSize) * this.pixelSize;
            const y = Math.floor(particle.y / this.pixelSize) * this.pixelSize;
            const size = Math.ceil(particle.size / this.pixelSize) * this.pixelSize;
            
            ctx.fillRect(x - size / 2, y - size / 2, size, size);
        });
        
        ctx.restore();
    }

    drawScreenFlashes(ctx) {
        this.screenFlashes.forEach(flash => {
            ctx.save();
            ctx.globalAlpha = flash.opacity * 0.5;
            ctx.fillStyle = flash.color;
            ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            ctx.restore();
        });
    }

    drawCRTEffect(ctx) {
        if (!this.crtEffect) return;

        ctx.save();
        
        ctx.globalAlpha = 0.05;
        for (let y = this.scanlineOffset; y < this.canvas.height; y += 4) {
            ctx.fillStyle = '#000000';
            ctx.fillRect(0, y, this.canvas.width, 2);
        }
        
        ctx.globalAlpha = 0.02;
        const gradient = ctx.createRadialGradient(
            this.canvas.width / 2, this.canvas.height / 2, 0,
            this.canvas.width / 2, this.canvas.height / 2, this.canvas.width / 2
        );
        gradient.addColorStop(0, 'transparent');
        gradient.addColorStop(1, '#000000');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        ctx.globalAlpha = 0.01;
        ctx.fillStyle = `rgb(${Math.random() * 20}, ${Math.random() * 20}, ${Math.random() * 20})`;
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        if (this.attractModeActive) {
            ctx.globalAlpha = this.glowIntensity * 0.1;
            ctx.fillStyle = '#00FF00';
            ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        }
        
        ctx.restore();
    }

    drawPixelGrid(ctx) {
        ctx.imageSmoothingEnabled = false;
        ctx.mozImageSmoothingEnabled = false;
        ctx.webkitImageSmoothingEnabled = false;
        ctx.msImageSmoothingEnabled = false;
    }

    startAttractMode() {
        this.attractModeActive = true;
        this.attractModeTimer = 0;
    }

    stopAttractMode() {
        this.attractModeActive = false;
        this.idleTimer = 0;
    }

    resetIdleTimer() {
        this.idleTimer = 0;
        if (this.attractModeActive) {
            this.stopAttractMode();
        }
    }

    render(ctx) {
        this.drawParticles(ctx);
        this.drawScreenFlashes(ctx);
        this.drawCRTEffect(ctx);
    }

    clear() {
        this.particles = [];
        this.screenFlashes = [];
    }
}

export default VisualEffects;