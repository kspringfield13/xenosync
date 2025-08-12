class ParticleSystem {
    constructor() {
        this.particles = [];
        this.maxParticles = 500;
        this.gravity = 0.1;
        this.friction = 0.98;
    }

    update(deltaTime) {
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const particle = this.particles[i];
            
            particle.life -= deltaTime;
            
            if (particle.life <= 0 || particle.opacity <= 0) {
                this.particles.splice(i, 1);
                continue;
            }
            
            particle.x += particle.vx * (deltaTime / 16);
            particle.y += particle.vy * (deltaTime / 16);
            
            if (particle.useGravity) {
                particle.vy += this.gravity * (deltaTime / 16);
            }
            
            particle.vx *= this.friction;
            particle.vy *= this.friction;
            
            const lifeRatio = particle.life / particle.maxLife;
            particle.opacity = particle.fadeOut ? lifeRatio : 1;
            
            if (particle.shrink) {
                particle.size = particle.originalSize * lifeRatio;
            }
            
            if (particle.pulse) {
                particle.size = particle.originalSize * (1 + Math.sin(particle.life * 0.01) * 0.3);
            }
            
            if (particle.rotate) {
                particle.rotation += particle.rotationSpeed * (deltaTime / 16);
            }
        }
    }

    createDotCollectionBurst(x, y) {
        const colors = ['#FFFF00', '#FFD700', '#FFA500'];
        const particleCount = 8;
        
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 / particleCount) * i;
            const speed = 1.5 + Math.random() * 1.5;
            const color = colors[Math.floor(Math.random() * colors.length)];
            
            this.addParticle({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 2,
                originalSize: 2,
                color: color,
                life: 300,
                maxLife: 300,
                opacity: 1,
                fadeOut: true,
                shrink: true,
                useGravity: false,
                type: 'dot'
            });
        }
    }

    createPowerPelletExplosion(x, y) {
        const colors = ['#FFFFFF', '#00FFFF', '#FFFF00', '#FF00FF'];
        const particleCount = 20;
        
        for (let i = 0; i < particleCount; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 2 + Math.random() * 3;
            const color = colors[Math.floor(Math.random() * colors.length)];
            
            this.addParticle({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 4,
                originalSize: 4,
                color: color,
                life: 500,
                maxLife: 500,
                opacity: 1,
                fadeOut: true,
                shrink: false,
                pulse: true,
                useGravity: false,
                type: 'power'
            });
        }
        
        for (let i = 0; i < 8; i++) {
            const angle = (Math.PI * 2 / 8) * i;
            this.createSparkTrail(x, y, angle);
        }
    }

    createSparkTrail(x, y, angle) {
        const trailLength = 5;
        for (let i = 0; i < trailLength; i++) {
            setTimeout(() => {
                const speed = 3 - i * 0.3;
                this.addParticle({
                    x: x,
                    y: y,
                    vx: Math.cos(angle) * speed,
                    vy: Math.sin(angle) * speed,
                    size: 3 - i * 0.4,
                    originalSize: 3 - i * 0.4,
                    color: '#FFFFFF',
                    life: 200,
                    maxLife: 200,
                    opacity: 1,
                    fadeOut: true,
                    shrink: true,
                    useGravity: false,
                    type: 'spark'
                });
            }, i * 30);
        }
    }

    createGhostEatenEffect(x, y, points) {
        this.createPointsDisplay(x, y, points);
        
        const colors = ['#00FFFF', '#FFFFFF'];
        const particleCount = 15;
        
        for (let i = 0; i < particleCount; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 1 + Math.random() * 2;
            const color = colors[Math.floor(Math.random() * colors.length)];
            
            this.addParticle({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 1,
                size: 3,
                originalSize: 3,
                color: color,
                life: 600,
                maxLife: 600,
                opacity: 1,
                fadeOut: true,
                shrink: true,
                useGravity: true,
                type: 'ghost'
            });
        }
    }

    createPointsDisplay(x, y, points) {
        this.addParticle({
            x: x,
            y: y,
            vx: 0,
            vy: -0.5,
            size: 1,
            text: points.toString(),
            color: '#FFFFFF',
            life: 1000,
            maxLife: 1000,
            opacity: 1,
            fadeOut: true,
            useGravity: false,
            type: 'text'
        });
    }

    createDeathExplosion(x, y) {
        const particleCount = 32;
        
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 / particleCount) * i;
            const speed = 2 + Math.random() * 2;
            
            this.addParticle({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 3,
                originalSize: 3,
                color: '#FFFF00',
                life: 800,
                maxLife: 800,
                opacity: 1,
                fadeOut: true,
                shrink: true,
                useGravity: false,
                rotate: true,
                rotation: 0,
                rotationSpeed: Math.random() * 0.2 - 0.1,
                type: 'death'
            });
        }
        
        for (let i = 0; i < 8; i++) {
            const angle = (Math.PI * 2 / 8) * i;
            const speed = 3;
            
            this.addParticle({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 5,
                originalSize: 5,
                color: '#FF0000',
                life: 400,
                maxLife: 400,
                opacity: 1,
                fadeOut: true,
                shrink: false,
                pulse: true,
                useGravity: false,
                type: 'death_pulse'
            });
        }
    }

    createFruitCollectionEffect(x, y, fruitType) {
        const colors = {
            cherry: ['#FF0000', '#00FF00'],
            strawberry: ['#FF0080', '#00FF00'],
            orange: ['#FFA500', '#FFD700'],
            apple: ['#FF0000', '#8B4513']
        };
        
        const fruitColors = colors[fruitType] || colors.cherry;
        const particleCount = 12;
        
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 / particleCount) * i;
            const speed = 2 + Math.random();
            const color = fruitColors[Math.floor(Math.random() * fruitColors.length)];
            
            this.addParticle({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 1,
                size: 4,
                originalSize: 4,
                color: color,
                life: 500,
                maxLife: 500,
                opacity: 1,
                fadeOut: true,
                shrink: true,
                useGravity: true,
                type: 'fruit'
            });
        }
    }

    createLevelCompleteEffect(canvasWidth, canvasHeight) {
        const colors = ['#FFFF00', '#00FFFF', '#FF00FF', '#00FF00', '#FF0000'];
        
        for (let x = 0; x < canvasWidth; x += 20) {
            setTimeout(() => {
                const particleCount = 3;
                for (let i = 0; i < particleCount; i++) {
                    const color = colors[Math.floor(Math.random() * colors.length)];
                    
                    this.addParticle({
                        x: x,
                        y: canvasHeight,
                        vx: (Math.random() - 0.5) * 2,
                        vy: -5 - Math.random() * 5,
                        size: 3 + Math.random() * 3,
                        originalSize: 3 + Math.random() * 3,
                        color: color,
                        life: 1500,
                        maxLife: 1500,
                        opacity: 1,
                        fadeOut: true,
                        shrink: false,
                        useGravity: true,
                        type: 'celebration'
                    });
                }
            }, x * 2);
        }
    }

    addParticle(properties) {
        if (this.particles.length >= this.maxParticles) {
            this.particles.shift();
        }
        
        this.particles.push({
            ...properties,
            id: Date.now() + Math.random()
        });
    }

    draw(ctx) {
        ctx.save();
        
        for (const particle of this.particles) {
            ctx.globalAlpha = particle.opacity;
            
            if (particle.type === 'text' && particle.text) {
                ctx.font = 'bold 14px monospace';
                ctx.fillStyle = particle.color;
                ctx.textAlign = 'center';
                ctx.fillText(particle.text, particle.x, particle.y);
            } else {
                ctx.fillStyle = particle.color;
                
                if (particle.rotate) {
                    ctx.save();
                    ctx.translate(particle.x, particle.y);
                    ctx.rotate(particle.rotation || 0);
                    ctx.fillRect(-particle.size / 2, -particle.size / 2, particle.size, particle.size);
                    ctx.restore();
                } else {
                    const pixelSize = Math.ceil(particle.size);
                    const pixelX = Math.floor(particle.x - pixelSize / 2);
                    const pixelY = Math.floor(particle.y - pixelSize / 2);
                    ctx.fillRect(pixelX, pixelY, pixelSize, pixelSize);
                }
            }
        }
        
        ctx.restore();
    }

    clear() {
        this.particles = [];
    }

    getParticleCount() {
        return this.particles.length;
    }
}

export default ParticleSystem;