class PowerUpManager {
    constructor(game) {
        this.game = game;
        this.isPowerUpActive = false;
        this.powerUpTimer = 0;
        this.powerUpDuration = 8000;
        this.warningTime = 2000;
        this.ghostsEaten = 0;
        this.ghostPointValues = [200, 400, 800, 1600];
        this.level = 1;
        
        this.flashInterval = null;
        this.isFlashing = false;
        this.flashState = false;
    }
    
    activatePowerUp() {
        this.isPowerUpActive = true;
        this.powerUpTimer = this.getPowerUpDuration();
        this.ghostsEaten = 0;
        
        if (this.flashInterval) {
            clearInterval(this.flashInterval);
        }
        
        this.makeGhostsVulnerable();
        
        if (this.game.soundManager) {
            this.game.soundManager.playPowerUpSound();
        }
    }
    
    getPowerUpDuration() {
        const baseDuration = 8000;
        const reduction = Math.min(this.level * 500, 5000);
        return Math.max(baseDuration - reduction, 3000);
    }
    
    update(deltaTime) {
        if (!this.isPowerUpActive) return;
        
        this.powerUpTimer -= deltaTime;
        
        if (this.powerUpTimer <= 0) {
            this.deactivatePowerUp();
        } else if (this.powerUpTimer <= this.warningTime && !this.isFlashing) {
            this.startFlashing();
        }
    }
    
    startFlashing() {
        this.isFlashing = true;
        this.flashState = false;
        
        this.flashInterval = setInterval(() => {
            this.flashState = !this.flashState;
            this.updateGhostAppearance();
        }, 200);
    }
    
    deactivatePowerUp() {
        this.isPowerUpActive = false;
        this.powerUpTimer = 0;
        this.isFlashing = false;
        this.flashState = false;
        
        if (this.flashInterval) {
            clearInterval(this.flashInterval);
            this.flashInterval = null;
        }
        
        this.makeGhostsNormal();
        
        if (this.game.soundManager) {
            this.game.soundManager.stopPowerUpSound();
        }
    }
    
    makeGhostsVulnerable() {
        if (!this.game.ghosts) return;
        
        this.game.ghosts.forEach(ghost => {
            if (ghost.state !== 'eaten' && ghost.state !== 'returning') {
                ghost.makeVulnerable();
            }
        });
    }
    
    makeGhostsNormal() {
        if (!this.game.ghosts) return;
        
        this.game.ghosts.forEach(ghost => {
            if (ghost.state === 'frightened') {
                ghost.makeNormal();
            }
        });
    }
    
    updateGhostAppearance() {
        if (!this.game.ghosts) return;
        
        this.game.ghosts.forEach(ghost => {
            if (ghost.state === 'frightened') {
                ghost.updateFlashState(this.flashState);
            }
        });
    }
    
    eatGhost(ghost) {
        if (!this.isPowerUpActive || ghost.state !== 'frightened') {
            return 0;
        }
        
        const points = this.ghostPointValues[Math.min(this.ghostsEaten, 3)];
        this.ghostsEaten++;
        
        ghost.setEaten();
        
        if (this.game.soundManager) {
            this.game.soundManager.playEatGhostSound();
        }
        
        return points;
    }
    
    reset() {
        this.deactivatePowerUp();
        this.ghostsEaten = 0;
    }
    
    setLevel(level) {
        this.level = level;
    }
}

class GhostVulnerability {
    constructor(ghost) {
        this.ghost = ghost;
        this.originalSpeed = ghost.speed;
        this.originalColor = ghost.color;
        this.vulnerableSpeed = ghost.speed * 0.5;
        this.returningSpeed = ghost.speed * 2;
        
        this.vulnerableColor = '#0000ff';
        this.flashingWhite = '#ffffff';
        this.eyesOnly = false;
    }
    
    makeVulnerable() {
        this.ghost.state = 'frightened';
        this.ghost.speed = this.vulnerableSpeed;
        this.ghost.color = this.vulnerableColor;
        this.eyesOnly = false;
        
        this.reverseDirection();
    }
    
    makeNormal() {
        this.ghost.state = 'chase';
        this.ghost.speed = this.originalSpeed;
        this.ghost.color = this.originalColor;
        this.eyesOnly = false;
    }
    
    setEaten() {
        this.ghost.state = 'returning';
        this.ghost.speed = this.returningSpeed;
        this.eyesOnly = true;
    }
    
    reverseDirection() {
        if (this.ghost.direction === 'up') {
            this.ghost.direction = 'down';
        } else if (this.ghost.direction === 'down') {
            this.ghost.direction = 'up';
        } else if (this.ghost.direction === 'left') {
            this.ghost.direction = 'right';
        } else if (this.ghost.direction === 'right') {
            this.ghost.direction = 'left';
        }
    }
    
    updateFlashState(isWhite) {
        if (this.ghost.state === 'frightened' && !this.eyesOnly) {
            this.ghost.color = isWhite ? this.flashingWhite : this.vulnerableColor;
        }
    }
    
    render(ctx, x, y, size) {
        if (this.eyesOnly) {
            this.renderEyes(ctx, x, y, size);
        } else if (this.ghost.state === 'frightened') {
            this.renderFrightened(ctx, x, y, size);
        } else {
            this.renderNormal(ctx, x, y, size);
        }
    }
    
    renderFrightened(ctx, x, y, size) {
        ctx.fillStyle = this.ghost.color;
        
        ctx.beginPath();
        ctx.arc(x + size/2, y + size/2, size/2 - 2, Math.PI, 0, false);
        
        const waves = 4;
        const waveHeight = 3;
        for (let i = 0; i <= waves; i++) {
            const wx = x + (size / waves) * i;
            const wy = y + size - waveHeight + (i % 2 === 0 ? 0 : waveHeight);
            if (i === 0) {
                ctx.lineTo(wx, wy);
            } else {
                ctx.lineTo(wx, wy);
            }
        }
        
        ctx.closePath();
        ctx.fill();
        
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(x + size * 0.25 - 2, y + size * 0.35, 4, 4);
        ctx.fillRect(x + size * 0.75 - 2, y + size * 0.35, 4, 4);
        
        ctx.beginPath();
        ctx.moveTo(x + size * 0.3, y + size * 0.65);
        ctx.lineTo(x + size * 0.35, y + size * 0.7);
        ctx.lineTo(x + size * 0.4, y + size * 0.65);
        ctx.lineTo(x + size * 0.45, y + size * 0.7);
        ctx.lineTo(x + size * 0.5, y + size * 0.65);
        ctx.lineTo(x + size * 0.55, y + size * 0.7);
        ctx.lineTo(x + size * 0.6, y + size * 0.65);
        ctx.lineTo(x + size * 0.65, y + size * 0.7);
        ctx.lineTo(x + size * 0.7, y + size * 0.65);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
    
    renderEyes(ctx, x, y, size) {
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(x + size * 0.3, y + size * 0.35, size * 0.15, 0, Math.PI * 2);
        ctx.arc(x + size * 0.7, y + size * 0.35, size * 0.15, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.fillStyle = '#000000';
        const eyeOffsetX = this.getEyeDirection().x * size * 0.08;
        const eyeOffsetY = this.getEyeDirection().y * size * 0.08;
        
        ctx.beginPath();
        ctx.arc(x + size * 0.3 + eyeOffsetX, y + size * 0.35 + eyeOffsetY, size * 0.08, 0, Math.PI * 2);
        ctx.arc(x + size * 0.7 + eyeOffsetX, y + size * 0.35 + eyeOffsetY, size * 0.08, 0, Math.PI * 2);
        ctx.fill();
    }
    
    renderNormal(ctx, x, y, size) {
        ctx.fillStyle = this.ghost.color;
        
        ctx.beginPath();
        ctx.arc(x + size/2, y + size/2, size/2 - 2, Math.PI, 0, false);
        
        const waves = 4;
        const waveHeight = 3;
        for (let i = 0; i <= waves; i++) {
            const wx = x + (size / waves) * i;
            const wy = y + size - waveHeight + (i % 2 === 0 ? 0 : waveHeight);
            if (i === 0) {
                ctx.lineTo(wx, wy);
            } else {
                ctx.lineTo(wx, wy);
            }
        }
        
        ctx.closePath();
        ctx.fill();
        
        this.renderEyes(ctx, x, y, size);
    }
    
    getEyeDirection() {
        switch(this.ghost.direction) {
            case 'up': return { x: 0, y: -1 };
            case 'down': return { x: 0, y: 1 };
            case 'left': return { x: -1, y: 0 };
            case 'right': return { x: 1, y: 0 };
            default: return { x: 0, y: 0 };
        }
    }
}

export { PowerUpManager, GhostVulnerability };