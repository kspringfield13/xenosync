class GameStates {
    constructor() {
        this.currentState = 'START_SCREEN';
        this.previousState = null;
        this.stateTimer = 0;
        this.transitions = {};
        
        // Game state data
        this.score = 0;
        this.highScore = this.loadHighScore();
        this.lives = GameConfig.INITIAL_LIVES;
        this.level = 1;
        this.dotsCollected = 0;
        this.totalDots = 0;
        this.ghostsEatenInPowerMode = 0;
        
        // UI elements
        this.initializeUIElements();
        
        // State transition callbacks
        this.onStateChange = null;
        
        // Attract mode demo
        this.attractModeTimer = 0;
        this.attractModePhase = 0;
    }
    
    // Initialize UI elements
    initializeUIElements() {
        this.screens = {
            startScreen: document.getElementById('start-screen'),
            gameOverScreen: document.getElementById('game-over-screen'),
            pauseScreen: document.getElementById('pause-screen'),
            levelTransitionScreen: document.getElementById('level-transition-screen')
        };
        
        this.hudElements = {
            score: document.getElementById('score'),
            highScore: document.getElementById('high-score'),
            highScoreValue: document.getElementById('high-score-value'),
            finalScore: document.getElementById('final-score'),
            lives: document.getElementById('lives-container'),
            level: document.getElementById('level'),
            levelNumber: document.getElementById('level-number')
        };
        
        // Update initial display
        this.updateHUD();
    }
    
    // State management
    setState(newState, data = {}) {
        if (this.currentState === newState) return;
        
        // Exit current state
        this.exitState(this.currentState);
        
        // Store previous state
        this.previousState = this.currentState;
        this.currentState = newState;
        this.stateTimer = 0;
        
        // Enter new state
        this.enterState(newState, data);
        
        // Trigger callback
        if (this.onStateChange) {
            this.onStateChange(newState, this.previousState);
        }
    }
    
    // Enter state
    enterState(state, data) {
        // Hide all screens first
        Object.values(this.screens).forEach(screen => {
            if (screen) screen.classList.remove('active');
        });
        
        switch(state) {
            case 'START_SCREEN':
                this.enterStartScreen();
                break;
                
            case 'GAME_READY':
                this.enterGameReady();
                break;
                
            case 'PLAYING':
                this.enterPlaying();
                break;
                
            case 'PAUSED':
                this.enterPaused();
                break;
                
            case 'LEVEL_COMPLETE':
                this.enterLevelComplete();
                break;
                
            case 'LEVEL_TRANSITION':
                this.enterLevelTransition();
                break;
                
            case 'DEATH':
                this.enterDeath();
                break;
                
            case 'GAME_OVER':
                this.enterGameOver();
                break;
        }
    }
    
    // Exit state
    exitState(state) {
        switch(state) {
            case 'START_SCREEN':
                this.exitStartScreen();
                break;
                
            case 'PAUSED':
                this.exitPaused();
                break;
        }
    }
    
    // Start screen state
    enterStartScreen() {
        if (this.screens.startScreen) {
            this.screens.startScreen.classList.add('active');
        }
        
        // Update high score display
        if (this.hudElements.highScoreValue) {
            this.hudElements.highScoreValue.textContent = this.highScore;
        }
        
        // Start attract mode
        this.attractModeTimer = 0;
        this.attractModePhase = 0;
    }
    
    exitStartScreen() {
        if (this.screens.startScreen) {
            this.screens.startScreen.classList.remove('active');
        }
    }
    
    // Game ready state (shows "READY!" message)
    enterGameReady() {
        // Show level transition screen with "READY!" message
        if (this.screens.levelTransitionScreen) {
            this.screens.levelTransitionScreen.classList.add('active');
            const readyMessage = this.screens.levelTransitionScreen.querySelector('.ready-message');
            if (readyMessage) {
                readyMessage.textContent = 'READY!';
            }
        }
        
        // Transition to playing after 2 seconds
        this.stateTimer = 2000;
    }
    
    // Playing state
    enterPlaying() {
        // Hide all overlay screens
        Object.values(this.screens).forEach(screen => {
            if (screen) screen.classList.remove('active');
        });
        
        // Reset power mode counter
        this.ghostsEatenInPowerMode = 0;
    }
    
    // Paused state
    enterPaused() {
        if (this.screens.pauseScreen) {
            this.screens.pauseScreen.classList.add('active');
        }
    }
    
    exitPaused() {
        if (this.screens.pauseScreen) {
            this.screens.pauseScreen.classList.remove('active');
        }
    }
    
    // Level complete state
    enterLevelComplete() {
        // Play level complete animation
        this.stateTimer = 2000; // 2 seconds before transition
    }
    
    // Level transition state
    enterLevelTransition() {
        this.level++;
        
        if (this.screens.levelTransitionScreen) {
            this.screens.levelTransitionScreen.classList.add('active');
            
            // Update level number
            if (this.hudElements.levelNumber) {
                this.hudElements.levelNumber.textContent = this.level;
            }
            
            const readyMessage = this.screens.levelTransitionScreen.querySelector('.ready-message');
            if (readyMessage) {
                readyMessage.textContent = 'GET READY!';
            }
        }
        
        // Update HUD
        this.updateHUD();
        
        // Transition to playing after 3 seconds
        this.stateTimer = 3000;
    }
    
    // Death state
    enterDeath() {
        this.lives--;
        this.updateHUD();
        
        // Play death animation
        assetManager.playSound('death');
        
        if (this.lives > 0) {
            // Show ready message after death animation
            this.stateTimer = 2000;
        } else {
            // No lives left, game over
            this.stateTimer = 2000;
        }
    }
    
    // Game over state
    enterGameOver() {
        if (this.screens.gameOverScreen) {
            this.screens.gameOverScreen.classList.add('active');
            
            // Update final score
            if (this.hudElements.finalScore) {
                this.hudElements.finalScore.textContent = this.score;
            }
        }
        
        // Save high score
        if (this.score > this.highScore) {
            this.highScore = this.score;
            this.saveHighScore();
        }
    }
    
    // Update state
    update(deltaTime) {
        this.stateTimer -= deltaTime;
        
        switch(this.currentState) {
            case 'START_SCREEN':
                this.updateStartScreen(deltaTime);
                break;
                
            case 'GAME_READY':
                if (this.stateTimer <= 0) {
                    this.setState('PLAYING');
                }
                break;
                
            case 'LEVEL_COMPLETE':
                if (this.stateTimer <= 0) {
                    this.setState('LEVEL_TRANSITION');
                }
                break;
                
            case 'LEVEL_TRANSITION':
                if (this.stateTimer <= 0) {
                    this.setState('PLAYING');
                }
                break;
                
            case 'DEATH':
                if (this.stateTimer <= 0) {
                    if (this.lives > 0) {
                        this.setState('GAME_READY');
                    } else {
                        this.setState('GAME_OVER');
                    }
                }
                break;
        }
    }
    
    // Update start screen (attract mode)
    updateStartScreen(deltaTime) {
        this.attractModeTimer += deltaTime;
        
        // Change attract mode phase every 5 seconds
        if (this.attractModeTimer > 5000) {
            this.attractModeTimer = 0;
            this.attractModePhase = (this.attractModePhase + 1) % 3;
        }
    }
    
    // Handle input
    handleInput(key) {
        switch(this.currentState) {
            case 'START_SCREEN':
                if (key === 'Enter') {
                    this.startNewGame();
                }
                break;
                
            case 'PLAYING':
                if (key === 'p' || key === 'P') {
                    this.togglePause();
                } else if (key === 'Escape') {
                    this.showMenu();
                }
                break;
                
            case 'PAUSED':
                if (key === 'p' || key === 'P') {
                    this.togglePause();
                }
                break;
                
            case 'GAME_OVER':
                if (key === 'Enter') {
                    this.setState('START_SCREEN');
                }
                break;
        }
    }
    
    // Start new game
    startNewGame() {
        this.score = 0;
        this.lives = GameConfig.INITIAL_LIVES;
        this.level = 1;
        this.dotsCollected = 0;
        this.updateHUD();
        
        this.setState('GAME_READY');
    }
    
    // Toggle pause
    togglePause() {
        if (this.currentState === 'PLAYING') {
            this.setState('PAUSED');
        } else if (this.currentState === 'PAUSED') {
            this.setState('PLAYING');
        }
    }
    
    // Show menu
    showMenu() {
        this.setState('START_SCREEN');
    }
    
    // Update HUD
    updateHUD() {
        // Update score
        if (this.hudElements.score) {
            this.hudElements.score.textContent = this.score;
        }
        
        // Update high score
        if (this.hudElements.highScore) {
            this.hudElements.highScore.textContent = this.highScore;
        }
        
        // Update lives
        if (this.hudElements.lives) {
            this.hudElements.lives.innerHTML = '';
            for (let i = 0; i < this.lives; i++) {
                const lifeIcon = document.createElement('div');
                lifeIcon.className = 'life-icon';
                this.hudElements.lives.appendChild(lifeIcon);
            }
        }
        
        // Update level
        if (this.hudElements.level) {
            this.hudElements.level.textContent = this.level;
        }
    }
    
    // Score management
    addScore(points) {
        this.score += points;
        
        // Check for extra life every 10000 points
        const oldLifeCount = Math.floor((this.score - points) / 10000);
        const newLifeCount = Math.floor(this.score / 10000);
        
        if (newLifeCount > oldLifeCount) {
            this.lives++;
            assetManager.playSound('extraLife');
        }
        
        // Update high score if needed
        if (this.score > this.highScore) {
            this.highScore = this.score;
        }
        
        this.updateHUD();
    }
    
    // Dot collection
    collectDot() {
        this.dotsCollected++;
        this.addScore(GameConfig.POINTS_PER_DOT);
        assetManager.playSound('chomp');
        
        // Check if level complete
        if (this.dotsCollected >= this.totalDots) {
            this.setState('LEVEL_COMPLETE');
        }
    }
    
    // Power pellet collection
    collectPowerPellet() {
        this.addScore(GameConfig.POINTS_PER_POWER_PELLET);
        this.ghostsEatenInPowerMode = 0;
        assetManager.playSound('powerPellet');
    }
    
    // Ghost eaten
    eatGhost() {
        const points = GameConfig.POINTS_PER_GHOST[Math.min(this.ghostsEatenInPowerMode, 3)];
        this.addScore(points);
        this.ghostsEatenInPowerMode++;
        assetManager.playSound('eatGhost');
        
        return points;
    }
    
    // Fruit collection
    collectFruit(fruitType) {
        const points = GameConfig.BONUS_FRUIT_POINTS[fruitType] || 100;
        this.addScore(points);
        assetManager.playSound('eatFruit');
        
        return points;
    }
    
    // High score persistence
    loadHighScore() {
        const stored = localStorage.getItem('pacman_highscore');
        return stored ? parseInt(stored) : 0;
    }
    
    saveHighScore() {
        localStorage.setItem('pacman_highscore', this.highScore.toString());
    }
    
    // Reset for new level
    resetForNewLevel() {
        this.dotsCollected = 0;
        this.ghostsEatenInPowerMode = 0;
    }
    
    // Get current state
    getState() {
        return this.currentState;
    }
    
    // Check if game is playable
    isPlayable() {
        return this.currentState === 'PLAYING';
    }
    
    // Check if game is paused
    isPaused() {
        return this.currentState === 'PAUSED';
    }
    
    // Draw attract mode demo
    drawAttractMode(ctx) {
        if (this.currentState !== 'START_SCREEN') return;
        
        ctx.save();
        ctx.globalAlpha = 0.3;
        
        // Draw demo based on phase
        switch(this.attractModePhase) {
            case 0:
                // Show Pac-Man chasing dots
                this.drawAttractPacMan(ctx);
                break;
                
            case 1:
                // Show ghosts chasing Pac-Man
                this.drawAttractChase(ctx);
                break;
                
            case 2:
                // Show power pellet mode
                this.drawAttractPower(ctx);
                break;
        }
        
        ctx.restore();
    }
    
    // Draw Pac-Man in attract mode
    drawAttractPacMan(ctx) {
        const time = this.attractModeTimer / 1000;
        const x = 100 + Math.cos(time) * 50;
        const y = 200 + Math.sin(time * 2) * 30;
        
        ctx.fillStyle = '#ffcc00';
        ctx.beginPath();
        ctx.arc(x, y, 15, 0.2 * Math.PI, 1.8 * Math.PI);
        ctx.lineTo(x, y);
        ctx.fill();
    }
    
    // Draw chase scene in attract mode
    drawAttractChase(ctx) {
        const time = this.attractModeTimer / 1000;
        const baseX = 50 + time * 30;
        
        // Draw Pac-Man
        ctx.fillStyle = '#ffcc00';
        ctx.beginPath();
        ctx.arc(baseX + 100, 200, 15, 0.2 * Math.PI, 1.8 * Math.PI);
        ctx.lineTo(baseX + 100, 200);
        ctx.fill();
        
        // Draw ghosts
        const ghostColors = ['#ff0000', '#ffb8ff', '#00ffff', '#ffb851'];
        ghostColors.forEach((color, i) => {
            ctx.fillStyle = color;
            ctx.fillRect(baseX - (i + 1) * 30, 190, 20, 20);
        });
    }
    
    // Draw power mode in attract mode
    drawAttractPower(ctx) {
        const time = this.attractModeTimer / 1000;
        const baseX = 300 - time * 30;
        
        // Draw Pac-Man (larger)
        ctx.fillStyle = '#ffcc00';
        ctx.beginPath();
        ctx.arc(baseX, 200, 20, 0.2 * Math.PI, 1.8 * Math.PI);
        ctx.lineTo(baseX, 200);
        ctx.fill();
        
        // Draw frightened ghosts
        ctx.fillStyle = '#0000ff';
        for (let i = 0; i < 4; i++) {
            ctx.fillRect(baseX + (i + 1) * 35, 190, 20, 20);
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GameStates;
}