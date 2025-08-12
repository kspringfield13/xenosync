class Renderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.offscreenCanvas = document.createElement('canvas');
        this.offscreenCtx = this.offscreenCanvas.getContext('2d');
        this.offscreenCanvas.width = canvas.width;
        this.offscreenCanvas.height = canvas.height;
        
        this.pixelPerfect = true;
        this.screenShake = 0;
        this.screenShakeIntensity = 0;
        this.chromaShift = false;
        this.chromaOffset = 0;
        this.bloomEffect = true;
        this.bloomIntensity = 0.3;
        
        this.setupPixelPerfectRendering();
    }

    setupPixelPerfectRendering() {
        this.ctx.imageSmoothingEnabled = false;
        this.ctx.mozImageSmoothingEnabled = false;
        this.ctx.webkitImageSmoothingEnabled = false;
        this.ctx.msImageSmoothingEnabled = false;
        
        this.offscreenCtx.imageSmoothingEnabled = false;
        this.offscreenCtx.mozImageSmoothingEnabled = false;
        this.offscreenCtx.webkitImageSmoothingEnabled = false;
        this.offscreenCtx.msImageSmoothingEnabled = false;
    }

    beginFrame() {
        this.offscreenCtx.fillStyle = '#000000';
        this.offscreenCtx.fillRect(0, 0, this.offscreenCanvas.width, this.offscreenCanvas.height);
        
        if (this.screenShake > 0) {
            const shakeX = (Math.random() - 0.5) * this.screenShakeIntensity;
            const shakeY = (Math.random() - 0.5) * this.screenShakeIntensity;
            this.offscreenCtx.translate(shakeX, shakeY);
        }
    }

    endFrame() {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        if (this.chromaShift) {
            this.applyChromaShift();
        } else {
            this.ctx.drawImage(this.offscreenCanvas, 0, 0);
        }
        
        if (this.bloomEffect) {
            this.applyBloom();
        }
    }

    applyChromaShift() {
        const imageData = this.offscreenCtx.getImageData(0, 0, this.offscreenCanvas.width, this.offscreenCanvas.height);
        const data = imageData.data;
        const output = this.ctx.createImageData(imageData);
        const outputData = output.data;
        
        const offset = Math.floor(this.chromaOffset);
        
        for (let i = 0; i < data.length; i += 4) {
            const pixelIndex = i / 4;
            const x = pixelIndex % this.offscreenCanvas.width;
            
            outputData[i] = data[i];
            
            const greenIndex = i + 1 - offset * 4;
            if (greenIndex >= 0 && greenIndex < data.length) {
                outputData[i + 1] = data[greenIndex];
            }
            
            const blueIndex = i + 2 + offset * 4;
            if (blueIndex >= 0 && blueIndex < data.length) {
                outputData[i + 2] = data[blueIndex];
            }
            
            outputData[i + 3] = data[i + 3];
        }
        
        this.ctx.putImageData(output, 0, 0);
    }

    applyBloom() {
        const tempCanvas = document.createElement('canvas');
        const tempCtx = tempCanvas.getContext('2d');
        tempCanvas.width = this.canvas.width / 4;
        tempCanvas.height = this.canvas.height / 4;
        
        tempCtx.filter = 'blur(2px)';
        tempCtx.drawImage(this.canvas, 0, 0, tempCanvas.width, tempCanvas.height);
        
        this.ctx.save();
        this.ctx.globalCompositeOperation = 'screen';
        this.ctx.globalAlpha = this.bloomIntensity;
        this.ctx.drawImage(tempCanvas, 0, 0, this.canvas.width, this.canvas.height);
        this.ctx.restore();
    }

    drawMaze(maze, tileSize, pulseTimer) {
        const wallColor = '#2121DE';
        const wallShadowColor = '#1010A0';
        const dotColor = '#FFB897';
        const pelletColor = '#FFB897';
        
        for (let y = 0; y < maze.length; y++) {
            for (let x = 0; x < maze[y].length; x++) {
                const tile = maze[y][x];
                const pixelX = x * tileSize;
                const pixelY = y * tileSize;
                
                switch (tile) {
                    case 1:
                        this.drawWall(pixelX, pixelY, tileSize, wallColor, wallShadowColor);
                        break;
                    case 2:
                        this.drawDot(pixelX + tileSize / 2, pixelY + tileSize / 2, tileSize);
                        break;
                    case 3:
                        this.drawPowerPellet(pixelX + tileSize / 2, pixelY + tileSize / 2, tileSize, pulseTimer);
                        break;
                }
            }
        }
    }

    drawWall(x, y, size, color, shadowColor) {
        this.offscreenCtx.fillStyle = shadowColor;
        this.offscreenCtx.fillRect(x + 1, y + 1, size, size);
        
        this.offscreenCtx.fillStyle = color;
        this.offscreenCtx.fillRect(x, y, size - 1, size - 1);
        
        this.offscreenCtx.fillStyle = '#000000';
        const inset = 2;
        this.offscreenCtx.fillRect(x + inset, y + inset, size - inset * 2, size - inset * 2);
        
        this.offscreenCtx.strokeStyle = color;
        this.offscreenCtx.lineWidth = 1;
        this.offscreenCtx.strokeRect(x + inset - 1, y + inset - 1, size - inset * 2 + 2, size - inset * 2 + 2);
    }

    drawDot(x, y, size) {
        this.offscreenCtx.fillStyle = '#FFB897';
        const dotSize = Math.max(2, size / 4);
        const pixelX = Math.floor(x - dotSize / 2);
        const pixelY = Math.floor(y - dotSize / 2);
        this.offscreenCtx.fillRect(pixelX, pixelY, dotSize, dotSize);
    }

    drawPowerPellet(x, y, size, pulseTimer) {
        const pulse = Math.sin(pulseTimer * 0.005) * 0.3 + 0.7;
        this.offscreenCtx.fillStyle = '#FFB897';
        const pelletSize = (size / 2) * pulse;
        
        this.offscreenCtx.save();
        this.offscreenCtx.translate(x, y);
        
        for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 4) {
            const px = Math.cos(angle) * pelletSize;
            const py = Math.sin(angle) * pelletSize;
            this.offscreenCtx.fillRect(px - 1, py - 1, 3, 3);
        }
        
        this.offscreenCtx.fillRect(-2, -2, 5, 5);
        this.offscreenCtx.restore();
    }

    drawEntity(entity, spriteAnimator) {
        if (entity.draw) {
            entity.draw(this.offscreenCtx);
        }
    }

    drawUI(score, highScore, lives, level) {
        this.offscreenCtx.save();
        
        this.offscreenCtx.font = '16px monospace';
        this.offscreenCtx.fillStyle = '#FFFFFF';
        this.offscreenCtx.fillText(`SCORE: ${score.toString().padStart(6, '0')}`, 10, 20);
        this.offscreenCtx.fillText(`HIGH: ${highScore.toString().padStart(6, '0')}`, 150, 20);
        this.offscreenCtx.fillText(`LEVEL: ${level}`, 290, 20);
        
        this.offscreenCtx.fillStyle = '#FFFF00';
        for (let i = 0; i < lives; i++) {
            this.drawLifeIcon(10 + i * 20, this.canvas.height - 20);
        }
        
        this.offscreenCtx.restore();
    }

    drawLifeIcon(x, y) {
        this.offscreenCtx.save();
        this.offscreenCtx.translate(x, y);
        
        this.offscreenCtx.beginPath();
        this.offscreenCtx.arc(0, 0, 6, 0.2 * Math.PI, 1.8 * Math.PI);
        this.offscreenCtx.lineTo(0, 0);
        this.offscreenCtx.closePath();
        this.offscreenCtx.fill();
        
        this.offscreenCtx.restore();
    }

    drawGameOver() {
        this.offscreenCtx.save();
        
        this.offscreenCtx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        this.offscreenCtx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        this.offscreenCtx.font = 'bold 32px monospace';
        this.offscreenCtx.fillStyle = '#FF0000';
        this.offscreenCtx.textAlign = 'center';
        this.offscreenCtx.fillText('GAME OVER', this.canvas.width / 2, this.canvas.height / 2);
        
        this.offscreenCtx.font = '16px monospace';
        this.offscreenCtx.fillStyle = '#FFFFFF';
        this.offscreenCtx.fillText('PRESS ENTER TO RESTART', this.canvas.width / 2, this.canvas.height / 2 + 40);
        
        this.offscreenCtx.restore();
    }

    drawReady() {
        this.offscreenCtx.save();
        
        this.offscreenCtx.font = 'bold 24px monospace';
        this.offscreenCtx.fillStyle = '#FFFF00';
        this.offscreenCtx.textAlign = 'center';
        this.offscreenCtx.fillText('READY!', this.canvas.width / 2, this.canvas.height / 2);
        
        this.offscreenCtx.restore();
    }

    addScreenShake(intensity, duration) {
        this.screenShake = duration;
        this.screenShakeIntensity = intensity;
    }

    updateScreenShake(deltaTime) {
        if (this.screenShake > 0) {
            this.screenShake -= deltaTime;
            if (this.screenShake <= 0) {
                this.screenShake = 0;
                this.screenShakeIntensity = 0;
            }
        }
    }

    enableChromaShift(offset = 2) {
        this.chromaShift = true;
        this.chromaOffset = offset;
    }

    disableChromaShift() {
        this.chromaShift = false;
    }

    setBloomIntensity(intensity) {
        this.bloomIntensity = Math.max(0, Math.min(1, intensity));
    }

    getContext() {
        return this.offscreenCtx;
    }
}

export default Renderer;