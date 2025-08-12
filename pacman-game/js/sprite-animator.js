class SpriteAnimator {
    constructor() {
        this.animations = new Map();
        this.pixelSize = 2;
        this.retroPalette = {
            pacman: '#FFFF00',
            pacmanDark: '#FFD700',
            blinky: '#FF0000',
            pinky: '#FFB8FF',
            inky: '#00FFFF',
            clyde: '#FFB852',
            frightened: '#0000FF',
            frightenedFlash: '#FFFFFF',
            eyes: '#FFFFFF',
            eyePupil: '#0000FF',
            dot: '#FFB897',
            powerPellet: '#FFB897',
            wall: '#2121DE',
            wallShadow: '#1010A0',
            black: '#000000',
            white: '#FFFFFF'
        };
        
        this.initializeAnimations();
    }

    initializeAnimations() {
        this.animations.set('pacman', {
            frames: 4,
            currentFrame: 0,
            frameTime: 100,
            timer: 0,
            loop: true
        });

        this.animations.set('ghost-normal', {
            frames: 2,
            currentFrame: 0,
            frameTime: 200,
            timer: 0,
            loop: true
        });

        this.animations.set('ghost-frightened', {
            frames: 2,
            currentFrame: 0,
            frameTime: 150,
            timer: 0,
            loop: true
        });

        this.animations.set('ghost-eyes', {
            frames: 1,
            currentFrame: 0,
            frameTime: 0,
            timer: 0,
            loop: false
        });

        this.animations.set('pacman-death', {
            frames: 11,
            currentFrame: 0,
            frameTime: 100,
            timer: 0,
            loop: false
        });

        this.animations.set('fruit-bounce', {
            frames: 2,
            currentFrame: 0,
            frameTime: 500,
            timer: 0,
            loop: true
        });
    }

    updateAnimation(animationName, deltaTime) {
        const animation = this.animations.get(animationName);
        if (!animation) return;

        animation.timer += deltaTime;
        if (animation.timer >= animation.frameTime) {
            animation.timer = 0;
            if (animation.loop) {
                animation.currentFrame = (animation.currentFrame + 1) % animation.frames;
            } else {
                animation.currentFrame = Math.min(animation.currentFrame + 1, animation.frames - 1);
            }
        }
    }

    drawPacman(ctx, x, y, size, direction, frame, mouthOpen = true) {
        ctx.save();
        ctx.translate(x, y);
        
        const pixelMap = this.getPacmanPixelMap(direction, mouthOpen, frame);
        this.drawPixelSprite(ctx, pixelMap, size, this.retroPalette.pacman);
        
        ctx.restore();
    }

    drawGhost(ctx, x, y, size, color, state, frame, direction) {
        ctx.save();
        ctx.translate(x, y);
        
        let pixelMap;
        let ghostColor;
        
        switch (state) {
            case 'frightened':
                ghostColor = frame % 2 === 0 ? this.retroPalette.frightened : this.retroPalette.frightenedFlash;
                pixelMap = this.getFrightenedGhostPixelMap(frame);
                break;
            case 'eyes':
                pixelMap = this.getGhostEyesPixelMap(direction);
                ghostColor = null;
                break;
            default:
                ghostColor = this.retroPalette[color] || color;
                pixelMap = this.getGhostPixelMap(frame, direction);
                break;
        }
        
        if (ghostColor) {
            this.drawPixelSprite(ctx, pixelMap, size, ghostColor);
        }
        
        if (state !== 'eyes') {
            this.drawGhostEyes(ctx, size, direction, state === 'frightened');
        } else {
            this.drawFloatingEyes(ctx, size, direction);
        }
        
        ctx.restore();
    }

    getPacmanPixelMap(direction, mouthOpen, frame) {
        const closed = [
            [0,0,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [0,1,1,1,1,1,1,0],
            [0,0,1,1,1,1,0,0]
        ];

        if (!mouthOpen || frame >= 2) {
            return closed;
        }

        const mouthAngle = frame === 0 ? 'wide' : 'medium';
        
        const rightMouth = mouthAngle === 'wide' ? [
            [0,0,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,0,0],
            [1,1,1,1,0,0,0,0],
            [1,1,1,1,0,0,0,0],
            [1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,0],
            [0,0,1,1,1,1,0,0]
        ] : [
            [0,0,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,0],
            [1,1,1,1,1,0,0,0],
            [1,1,1,1,1,0,0,0],
            [1,1,1,1,1,1,1,0],
            [0,1,1,1,1,1,1,0],
            [0,0,1,1,1,1,0,0]
        ];

        switch (direction) {
            case 'left':
                return rightMouth.map(row => row.slice().reverse());
            case 'up':
                return this.rotatePixelMap(rightMouth, -90);
            case 'down':
                return this.rotatePixelMap(rightMouth, 90);
            default:
                return rightMouth;
        }
    }

    getGhostPixelMap(frame, direction) {
        const ghost = [
            [0,0,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1],
            [1,0,1,1,0,0,1,1]
        ];

        if (frame % 2 === 1) {
            ghost[7] = [1,1,0,1,1,1,0,1];
        }

        return ghost;
    }

    getFrightenedGhostPixelMap(frame) {
        return [
            [0,0,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,1],
            [1,0,1,1,1,1,0,1],
            [1,1,1,1,1,1,1,1],
            [1,1,0,0,0,0,1,1],
            [1,0,1,0,0,1,0,1],
            [0,1,0,1,1,0,1,0]
        ];
    }

    getGhostEyesPixelMap(direction) {
        return [
            [0,0,0,0,0,0,0,0],
            [0,1,1,0,0,1,1,0],
            [1,1,1,1,1,1,1,1],
            [1,0,0,1,1,0,0,1],
            [0,1,1,0,0,1,1,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0]
        ];
    }

    drawGhostEyes(ctx, size, direction, frightened) {
        const eyeSize = size / 8;
        const eyeOffset = size / 4;
        
        ctx.fillStyle = this.retroPalette.eyes;
        ctx.fillRect(-eyeOffset - eyeSize, -eyeOffset, eyeSize * 2, eyeSize * 2);
        ctx.fillRect(eyeOffset - eyeSize, -eyeOffset, eyeSize * 2, eyeSize * 2);
        
        if (!frightened) {
            ctx.fillStyle = this.retroPalette.eyePupil;
            let pupilX = 0;
            let pupilY = 0;
            
            switch (direction) {
                case 'left': pupilX = -eyeSize / 2; break;
                case 'right': pupilX = eyeSize / 2; break;
                case 'up': pupilY = -eyeSize / 2; break;
                case 'down': pupilY = eyeSize / 2; break;
            }
            
            ctx.fillRect(-eyeOffset + pupilX, -eyeOffset + pupilY, eyeSize, eyeSize);
            ctx.fillRect(eyeOffset + pupilX, -eyeOffset + pupilY, eyeSize, eyeSize);
        } else {
            ctx.fillStyle = this.retroPalette.white;
            ctx.fillRect(-eyeOffset, -eyeOffset + eyeSize / 2, eyeSize, eyeSize / 2);
            ctx.fillRect(eyeOffset, -eyeOffset + eyeSize / 2, eyeSize, eyeSize / 2);
        }
    }

    drawFloatingEyes(ctx, size, direction) {
        this.drawGhostEyes(ctx, size, direction, false);
    }

    drawPixelSprite(ctx, pixelMap, size, color) {
        const pixelSize = size / pixelMap.length;
        ctx.fillStyle = color;
        
        for (let y = 0; y < pixelMap.length; y++) {
            for (let x = 0; x < pixelMap[y].length; x++) {
                if (pixelMap[y][x] === 1) {
                    const px = Math.floor((x - pixelMap[y].length / 2) * pixelSize);
                    const py = Math.floor((y - pixelMap.length / 2) * pixelSize);
                    ctx.fillRect(px, py, Math.ceil(pixelSize), Math.ceil(pixelSize));
                }
            }
        }
    }

    rotatePixelMap(map, degrees) {
        const radians = (degrees * Math.PI) / 180;
        const cos = Math.cos(radians);
        const sin = Math.sin(radians);
        const size = map.length;
        const rotated = Array(size).fill().map(() => Array(size).fill(0));
        
        const cx = size / 2 - 0.5;
        const cy = size / 2 - 0.5;
        
        for (let y = 0; y < size; y++) {
            for (let x = 0; x < size; x++) {
                const dx = x - cx;
                const dy = y - cy;
                const nx = Math.round(dx * cos - dy * sin + cx);
                const ny = Math.round(dx * sin + dy * cos + cy);
                
                if (nx >= 0 && nx < size && ny >= 0 && ny < size) {
                    rotated[ny][nx] = map[y][x];
                }
            }
        }
        
        return rotated;
    }

    drawDeathAnimation(ctx, x, y, size, frame) {
        ctx.save();
        ctx.translate(x, y);
        
        const totalFrames = 11;
        const angle = (frame / totalFrames) * Math.PI;
        
        ctx.fillStyle = this.retroPalette.pacman;
        ctx.beginPath();
        
        if (frame < totalFrames) {
            ctx.arc(0, 0, size / 2, angle, Math.PI * 2 - angle);
            ctx.lineTo(0, 0);
        } else {
            ctx.arc(0, 0, Math.max(0, size / 2 * (1 - (frame - totalFrames) / 5)), 0, Math.PI * 2);
        }
        
        ctx.closePath();
        ctx.fill();
        
        ctx.restore();
    }

    drawDot(ctx, x, y, size) {
        ctx.fillStyle = this.retroPalette.dot;
        const dotSize = Math.max(2, size / 4);
        ctx.fillRect(x - dotSize / 2, y - dotSize / 2, dotSize, dotSize);
    }

    drawPowerPellet(ctx, x, y, size, pulse) {
        ctx.fillStyle = this.retroPalette.powerPellet;
        const baseSize = size / 2;
        const pelletSize = baseSize + Math.sin(pulse) * baseSize * 0.3;
        
        ctx.beginPath();
        ctx.arc(x, y, pelletSize, 0, Math.PI * 2);
        ctx.fill();
    }

    drawFruit(ctx, x, y, size, type, frame) {
        const bounce = Math.sin(frame * 0.1) * 2;
        ctx.save();
        ctx.translate(x, y + bounce);
        
        switch (type) {
            case 'cherry':
                this.drawCherry(ctx, size);
                break;
            case 'strawberry':
                this.drawStrawberry(ctx, size);
                break;
            case 'orange':
                this.drawOrange(ctx, size);
                break;
            case 'apple':
                this.drawApple(ctx, size);
                break;
            default:
                this.drawCherry(ctx, size);
        }
        
        ctx.restore();
    }

    drawCherry(ctx, size) {
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(-size / 4, 0, size / 3, 0, Math.PI * 2);
        ctx.arc(size / 4, 0, size / 3, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.strokeStyle = '#00FF00';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, -size / 3);
        ctx.lineTo(0, -size / 2);
        ctx.stroke();
    }

    drawStrawberry(ctx, size) {
        ctx.fillStyle = '#FF0080';
        ctx.beginPath();
        ctx.moveTo(0, -size / 2);
        ctx.lineTo(-size / 3, 0);
        ctx.lineTo(0, size / 2);
        ctx.lineTo(size / 3, 0);
        ctx.closePath();
        ctx.fill();
        
        ctx.fillStyle = '#00FF00';
        ctx.fillRect(-size / 4, -size / 2, size / 2, size / 6);
    }

    drawOrange(ctx, size) {
        ctx.fillStyle = '#FFA500';
        ctx.beginPath();
        ctx.arc(0, 0, size / 2, 0, Math.PI * 2);
        ctx.fill();
    }

    drawApple(ctx, size) {
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(0, 0, size / 2, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.fillStyle = '#8B4513';
        ctx.fillRect(-1, -size / 2, 2, size / 4);
    }

    resetAnimation(animationName) {
        const animation = this.animations.get(animationName);
        if (animation) {
            animation.currentFrame = 0;
            animation.timer = 0;
        }
    }

    getAnimationFrame(animationName) {
        const animation = this.animations.get(animationName);
        return animation ? animation.currentFrame : 0;
    }
}

export default SpriteAnimator;