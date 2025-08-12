class ScoreDisplay {
    constructor(scoringSystem) {
        this.scoringSystem = scoringSystem;
        this.canvas = null;
        this.ctx = null;
        this.retroFont = '16px "Courier New", monospace';
        this.largeRetroFont = '24px "Courier New", monospace';
        this.colors = {
            score: '#FFFFFF',
            highScore: '#FFFF00',
            popup: '#00FFFF',
            ghostPopup: '#FF00FF',
            fruitPopup: '#FF0000',
            shadow: 'rgba(0, 0, 0, 0.5)'
        };
    }

    init(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        
        this.scoringSystem.onScoreUpdate = (score, highScore) => {
            this.render();
        };
        
        this.scoringSystem.onLevelComplete = (level) => {
            this.showLevelComplete(level);
        };
    }

    render() {
        if (!this.ctx) return;
        
        this.ctx.save();
        
        this.drawScore();
        this.drawHighScore();
        this.drawLevel();
        this.drawProgress();
        this.drawPointPopups();
        this.drawFruit();
        
        this.ctx.restore();
    }

    drawScore() {
        this.ctx.font = this.largeRetroFont;
        this.ctx.fillStyle = this.colors.shadow;
        this.ctx.fillText('SCORE', 12, 27);
        this.ctx.fillStyle = this.colors.score;
        this.ctx.fillText('SCORE', 10, 25);
        
        const scoreText = this.formatScore(this.scoringSystem.score);
        this.ctx.fillStyle = this.colors.shadow;
        this.ctx.fillText(scoreText, 12, 52);
        this.ctx.fillStyle = this.colors.score;
        this.ctx.fillText(scoreText, 10, 50);
    }

    drawHighScore() {
        const x = this.canvas.width - 200;
        
        this.ctx.font = this.largeRetroFont;
        this.ctx.fillStyle = this.colors.shadow;
        this.ctx.fillText('HIGH', x + 2, 27);
        this.ctx.fillStyle = this.colors.highScore;
        this.ctx.fillText('HIGH', x, 25);
        
        const highScoreText = this.formatScore(this.scoringSystem.highScore);
        this.ctx.fillStyle = this.colors.shadow;
        this.ctx.fillText(highScoreText, x + 2, 52);
        this.ctx.fillStyle = this.colors.highScore;
        this.ctx.fillText(highScoreText, x, 50);
    }

    drawLevel() {
        const centerX = this.canvas.width / 2;
        
        this.ctx.font = this.retroFont;
        this.ctx.textAlign = 'center';
        
        const levelText = `LEVEL ${this.scoringSystem.level}`;
        this.ctx.fillStyle = this.colors.shadow;
        this.ctx.fillText(levelText, centerX + 1, 26);
        this.ctx.fillStyle = this.colors.score;
        this.ctx.fillText(levelText, centerX, 25);
        
        this.ctx.textAlign = 'left';
    }

    drawProgress() {
        const centerX = this.canvas.width / 2;
        const y = 45;
        const barWidth = 150;
        const barHeight = 8;
        const progress = this.scoringSystem.getProgress();
        
        this.ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
        this.ctx.fillRect(centerX - barWidth/2, y, barWidth, barHeight);
        
        this.ctx.fillStyle = '#FFFF00';
        const fillWidth = (progress.progress / 100) * barWidth;
        this.ctx.fillRect(centerX - barWidth/2, y, fillWidth, barHeight);
        
        this.ctx.strokeStyle = '#FFFFFF';
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(centerX - barWidth/2, y, barWidth, barHeight);
        
        this.ctx.font = '10px "Courier New", monospace';
        this.ctx.textAlign = 'center';
        this.ctx.fillStyle = this.colors.score;
        this.ctx.fillText(`${progress.dotsCollected}/${progress.totalDots}`, centerX, y + 20);
        this.ctx.textAlign = 'left';
    }

    drawPointPopups() {
        this.scoringSystem.pointPopups.forEach(popup => {
            this.ctx.save();
            this.ctx.globalAlpha = popup.opacity;
            
            let color = this.colors.popup;
            if (popup.isGhost) {
                color = this.colors.ghostPopup;
            } else if (popup.fruitType) {
                color = this.colors.fruitPopup;
            }
            
            this.ctx.font = popup.isGhost || popup.fruitType ? this.largeRetroFont : this.retroFont;
            this.ctx.fillStyle = color;
            this.ctx.strokeStyle = this.colors.shadow;
            this.ctx.lineWidth = 3;
            
            const text = popup.points.toString();
            const x = popup.x * 16;
            const y = popup.y * 16;
            
            this.ctx.strokeText(text, x, y);
            this.ctx.fillText(text, x, y);
            
            if (popup.fruitType) {
                this.ctx.font = '12px "Courier New", monospace';
                this.ctx.fillText(popup.fruitType.toUpperCase(), x, y + 15);
            }
            
            this.ctx.restore();
        });
        
        this.scoringSystem.updatePointPopups();
    }

    drawFruit() {
        if (!this.scoringSystem.currentFruit) return;
        
        const fruit = this.scoringSystem.currentFruit;
        const x = this.canvas.width - 100;
        const y = this.canvas.height - 50;
        
        this.ctx.font = '12px "Courier New", monospace';
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.fillText('BONUS:', x, y);
        
        this.ctx.fillStyle = this.getFruitColor(fruit.type);
        this.ctx.fillText(fruit.type.toUpperCase(), x, y + 15);
        
        this.ctx.fillStyle = '#FFFF00';
        this.ctx.fillText(this.scoringSystem.fruitPoints[fruit.type].toString(), x, y + 30);
    }

    getFruitColor(fruitType) {
        const colors = {
            cherry: '#FF0000',
            strawberry: '#FF69B4',
            orange: '#FFA500',
            apple: '#FF0000',
            melon: '#00FF00',
            galaxian: '#0000FF',
            bell: '#FFFF00',
            key: '#C0C0C0'
        };
        return colors[fruitType] || '#FFFFFF';
    }

    formatScore(score) {
        return score.toString().padStart(7, '0');
    }

    showLevelComplete(level) {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        
        let alpha = 0;
        const fadeIn = setInterval(() => {
            alpha += 0.05;
            if (alpha >= 1) {
                alpha = 1;
                clearInterval(fadeIn);
                
                setTimeout(() => {
                    const fadeOut = setInterval(() => {
                        alpha -= 0.05;
                        if (alpha <= 0) {
                            clearInterval(fadeOut);
                        }
                    }, 50);
                }, 2000);
            }
            
            this.ctx.save();
            this.ctx.globalAlpha = alpha;
            
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
            this.ctx.fillRect(0, centerY - 60, this.canvas.width, 120);
            
            this.ctx.font = '48px "Courier New", monospace';
            this.ctx.textAlign = 'center';
            this.ctx.fillStyle = '#FFFF00';
            this.ctx.strokeStyle = '#000000';
            this.ctx.lineWidth = 4;
            
            this.ctx.strokeText('LEVEL COMPLETE!', centerX, centerY);
            this.ctx.fillText('LEVEL COMPLETE!', centerX, centerY);
            
            this.ctx.font = '24px "Courier New", monospace';
            this.ctx.fillStyle = '#FFFFFF';
            this.ctx.fillText(`ENTERING LEVEL ${level}`, centerX, centerY + 40);
            
            this.ctx.textAlign = 'left';
            this.ctx.restore();
        }, 50);
    }

    drawGameOver() {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        
        this.ctx.save();
        
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        this.ctx.fillRect(0, centerY - 80, this.canvas.width, 160);
        
        this.ctx.font = '48px "Courier New", monospace';
        this.ctx.textAlign = 'center';
        this.ctx.fillStyle = '#FF0000';
        this.ctx.strokeStyle = '#FFFFFF';
        this.ctx.lineWidth = 3;
        
        this.ctx.strokeText('GAME OVER', centerX, centerY);
        this.ctx.fillText('GAME OVER', centerX, centerY);
        
        const progress = this.scoringSystem.getProgress();
        this.ctx.font = '20px "Courier New", monospace';
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.fillText(`FINAL SCORE: ${this.formatScore(progress.score)}`, centerX, centerY + 40);
        
        if (progress.score === progress.highScore && progress.score > 0) {
            this.ctx.fillStyle = '#FFFF00';
            this.ctx.fillText('NEW HIGH SCORE!', centerX, centerY + 70);
        }
        
        this.ctx.textAlign = 'left';
        this.ctx.restore();
    }
}

export default ScoreDisplay;