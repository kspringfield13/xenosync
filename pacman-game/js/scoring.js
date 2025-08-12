class ScoringSystem {
    constructor() {
        this.score = 0;
        this.highScore = this.loadHighScore();
        this.dotsCollected = 0;
        this.totalDots = 0;
        this.ghostCombo = 0;
        this.ghostComboTimer = null;
        this.pointsPerDot = 10;
        this.pointsPerPowerPellet = 50;
        this.ghostBasePoints = 200;
        this.fruitPoints = {
            cherry: 100,
            strawberry: 300,
            orange: 500,
            apple: 700,
            melon: 1000,
            galaxian: 2000,
            bell: 3000,
            key: 5000
        };
        this.currentFruit = null;
        this.fruitTimer = null;
        this.pointPopups = [];
        this.level = 1;
    }

    collectDot() {
        this.score += this.pointsPerDot;
        this.dotsCollected++;
        this.updateScore();
        this.createPointPopup(this.pointsPerDot);
        
        if (this.dotsCollected >= this.totalDots) {
            this.levelComplete();
        }
        
        return this.pointsPerDot;
    }

    collectPowerPellet() {
        this.score += this.pointsPerPowerPellet;
        this.dotsCollected++;
        this.ghostCombo = 0;
        this.updateScore();
        this.createPointPopup(this.pointsPerPowerPellet);
        
        if (this.dotsCollected >= this.totalDots) {
            this.levelComplete();
        }
        
        return this.pointsPerPowerPellet;
    }

    eatGhost() {
        const points = this.ghostBasePoints * Math.pow(2, this.ghostCombo);
        this.score += points;
        this.ghostCombo++;
        this.updateScore();
        this.createPointPopup(points, true);
        
        clearTimeout(this.ghostComboTimer);
        this.ghostComboTimer = setTimeout(() => {
            this.ghostCombo = 0;
        }, 10000);
        
        return points;
    }

    collectFruit(fruitType) {
        const points = this.fruitPoints[fruitType] || 100;
        this.score += points;
        this.updateScore();
        this.createPointPopup(points, false, fruitType);
        this.currentFruit = null;
        clearTimeout(this.fruitTimer);
        
        return points;
    }

    spawnFruit() {
        if (this.currentFruit) return;
        
        const fruitsByLevel = [
            'cherry',
            'strawberry',
            'orange',
            'orange',
            'apple',
            'apple',
            'melon',
            'melon',
            'galaxian',
            'galaxian',
            'bell',
            'bell',
            'key'
        ];
        
        const fruitType = fruitsByLevel[Math.min(this.level - 1, fruitsByLevel.length - 1)];
        this.currentFruit = {
            type: fruitType,
            x: 14,
            y: 17,
            active: true
        };
        
        this.fruitTimer = setTimeout(() => {
            this.currentFruit = null;
        }, 10000);
        
        return this.currentFruit;
    }

    shouldSpawnFruit() {
        const dotsForFruit = [70, 170];
        return dotsForFruit.includes(this.dotsCollected);
    }

    createPointPopup(points, isGhost = false, fruitType = null) {
        const popup = {
            points: points,
            x: 0,
            y: 0,
            opacity: 1.0,
            timer: 60,
            isGhost: isGhost,
            fruitType: fruitType
        };
        
        this.pointPopups.push(popup);
        
        setTimeout(() => {
            const index = this.pointPopups.indexOf(popup);
            if (index > -1) {
                this.pointPopups.splice(index, 1);
            }
        }, 1000);
    }

    updatePointPopups() {
        this.pointPopups.forEach(popup => {
            popup.y -= 0.5;
            popup.opacity = Math.max(0, popup.opacity - 0.02);
            popup.timer--;
        });
        
        this.pointPopups = this.pointPopups.filter(popup => popup.timer > 0);
    }

    setPopupPosition(popup, x, y) {
        popup.x = x;
        popup.y = y;
    }

    levelComplete() {
        this.level++;
        this.dotsCollected = 0;
        this.ghostCombo = 0;
        clearTimeout(this.ghostComboTimer);
        clearTimeout(this.fruitTimer);
        this.currentFruit = null;
        
        if (this.onLevelComplete) {
            this.onLevelComplete(this.level);
        }
    }

    resetLevel(totalDots) {
        this.dotsCollected = 0;
        this.totalDots = totalDots;
        this.ghostCombo = 0;
        this.currentFruit = null;
        clearTimeout(this.ghostComboTimer);
        clearTimeout(this.fruitTimer);
    }

    updateScore() {
        if (this.score > this.highScore) {
            this.highScore = this.score;
            this.saveHighScore();
        }
        
        if (this.onScoreUpdate) {
            this.onScoreUpdate(this.score, this.highScore);
        }
    }

    loadHighScore() {
        const saved = localStorage.getItem('pacman_highscore');
        return saved ? parseInt(saved) : 0;
    }

    saveHighScore() {
        localStorage.setItem('pacman_highscore', this.highScore.toString());
    }

    reset() {
        this.score = 0;
        this.dotsCollected = 0;
        this.ghostCombo = 0;
        this.level = 1;
        this.currentFruit = null;
        this.pointPopups = [];
        clearTimeout(this.ghostComboTimer);
        clearTimeout(this.fruitTimer);
        this.updateScore();
    }

    getProgress() {
        return {
            score: this.score,
            highScore: this.highScore,
            level: this.level,
            dotsCollected: this.dotsCollected,
            totalDots: this.totalDots,
            progress: this.totalDots > 0 ? (this.dotsCollected / this.totalDots) * 100 : 0
        };
    }
}

export default ScoringSystem;