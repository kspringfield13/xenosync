class UI {
    constructor(gameStates) {
        this.gameStates = gameStates;
        this.messageQueue = [];
        this.currentMessage = null;
        this.messageTimer = 0;
        
        // Point display animations
        this.pointDisplays = [];
        
        // Screen flash effect
        this.flashTimer = 0;
        this.flashColor = null;
        
        // Bonus fruit display
        this.currentFruit = null;
        this.fruitTimer = 0;
        
        // Initialize UI controls
        this.initializeControls();
    }
    
    // Initialize UI controls
    initializeControls() {
        // Keyboard controls
        document.addEventListener('keydown', (e) => this.handleKeyDown(e));
        document.addEventListener('keyup', (e) => this.handleKeyUp(e));
        
        // Button controls
        const startButton = document.querySelector('.start-button');
        const coinButton = document.querySelector('.coin-button');
        
        if (startButton) {
            startButton.addEventListener('click', () => {
                this.handleStartButton();
            });
        }
        
        if (coinButton) {
            coinButton.addEventListener('click', () => {
                this.handleCoinButton();
            });
        }
        
        // Touch controls for mobile
        this.initializeTouchControls();
    }
    
    // Initialize touch controls
    initializeTouchControls() {
        const canvas = document.getElementById('gameCanvas');
        if (!canvas) return;
        
        let touchStartX = 0;
        let touchStartY = 0;
        
        canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            const touch = e.touches[0];
            touchStartX = touch.clientX;
            touchStartY = touch.clientY;
        });
        
        canvas.addEventListener('touchmove', (e) => {
            e.preventDefault();
        });
        
        canvas.addEventListener('touchend', (e) => {
            e.preventDefault();
            const touch = e.changedTouches[0];
            const deltaX = touch.clientX - touchStartX;
            const deltaY = touch.clientY - touchStartY;
            
            // Determine swipe direction
            if (Math.abs(deltaX) > Math.abs(deltaY)) {
                // Horizontal swipe
                if (deltaX > 0) {
                    this.handleSwipe('right');
                } else {
                    this.handleSwipe('left');
                }
            } else {
                // Vertical swipe
                if (deltaY > 0) {
                    this.handleSwipe('down');
                } else {
                    this.handleSwipe('up');
                }
            }
        });
    }
    
    // Handle keyboard input
    handleKeyDown(e) {
        // Pass to game states for menu navigation
        this.gameStates.handleInput(e.key);
        
        // Game-specific controls
        if (this.gameStates.isPlayable()) {
            switch(e.key) {
                case 'ArrowUp':
                case 'w':
                case 'W':
                    this.onDirectionInput('up');
                    break;
                    
                case 'ArrowDown':
                case 's':
                case 'S':
                    this.onDirectionInput('down');
                    break;
                    
                case 'ArrowLeft':
                case 'a':
                case 'A':
                    this.onDirectionInput('left');
                    break;
                    
                case 'ArrowRight':
                case 'd':
                case 'D':
                    this.onDirectionInput('right');
                    break;
            }
        }
        
        // Prevent default for game keys
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)) {
            e.preventDefault();
        }
    }
    
    handleKeyUp(e) {
        // Handle key release if needed
    }
    
    // Handle swipe input
    handleSwipe(direction) {
        if (this.gameStates.isPlayable()) {
            this.onDirectionInput(direction);
        }
    }
    
    // Handle start button
    handleStartButton() {
        if (this.gameStates.getState() === 'START_SCREEN') {
            this.gameStates.startNewGame();
        } else if (this.gameStates.getState() === 'GAME_OVER') {
            this.gameStates.setState('START_SCREEN');
        }
    }
    
    // Handle coin button (for arcade feel)
    handleCoinButton() {
        this.showMessage('CREDIT 1', 1000);
        assetManager.playSound('coin');
    }
    
    // Direction input callback (to be set by game)
    onDirectionInput(direction) {
        // This will be overridden by the main game
    }
    
    // Show a temporary message
    showMessage(text, duration = 2000, color = '#ffffff') {
        this.messageQueue.push({
            text: text,
            duration: duration,
            color: color
        });
    }
    
    // Show points at position
    showPoints(x, y, points, color = '#ffffff') {
        this.pointDisplays.push({
            x: x,
            y: y,
            points: points,
            color: color,
            timer: 1000,
            offsetY: 0
        });
    }
    
    // Flash screen effect
    flashScreen(color = '#ffffff', duration = 200) {
        this.flashColor = color;
        this.flashTimer = duration;
    }
    
    // Show bonus fruit
    showFruit(fruitType) {
        this.currentFruit = fruitType;
        this.fruitTimer = 10000; // Show for 10 seconds
    }
    
    // Update UI elements
    update(deltaTime) {
        // Update message display
        this.updateMessages(deltaTime);
        
        // Update point displays
        this.updatePointDisplays(deltaTime);
        
        // Update screen flash
        this.updateFlash(deltaTime);
        
        // Update fruit timer
        this.updateFruit(deltaTime);
    }
    
    // Update message queue
    updateMessages(deltaTime) {
        if (this.currentMessage) {
            this.messageTimer -= deltaTime;
            if (this.messageTimer <= 0) {
                this.currentMessage = null;
            }
        } else if (this.messageQueue.length > 0) {
            this.currentMessage = this.messageQueue.shift();
            this.messageTimer = this.currentMessage.duration;
        }
    }
    
    // Update point displays
    updatePointDisplays(deltaTime) {
        this.pointDisplays = this.pointDisplays.filter(display => {
            display.timer -= deltaTime;
            display.offsetY -= deltaTime * 0.02; // Float upward
            return display.timer > 0;
        });
    }
    
    // Update screen flash
    updateFlash(deltaTime) {
        if (this.flashTimer > 0) {
            this.flashTimer -= deltaTime;
        }
    }
    
    // Update fruit display
    updateFruit(deltaTime) {
        if (this.fruitTimer > 0) {
            this.fruitTimer -= deltaTime;
            if (this.fruitTimer <= 0) {
                this.currentFruit = null;
            }
        }
    }
    
    // Draw UI elements
    draw(ctx) {
        // Draw screen flash
        if (this.flashTimer > 0) {
            ctx.save();
            ctx.globalAlpha = this.flashTimer / 200;
            ctx.fillStyle = this.flashColor;
            ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
            ctx.restore();
        }
        
        // Draw current message
        if (this.currentMessage) {
            this.drawMessage(ctx, this.currentMessage);
        }
        
        // Draw point displays
        this.pointDisplays.forEach(display => {
            this.drawPointDisplay(ctx, display);
        });
        
        // Draw bonus fruit indicator
        if (this.currentFruit) {
            this.drawFruitIndicator(ctx);
        }
        
        // Draw debug info if enabled
        if (window.DEBUG_MODE) {
            this.drawDebugInfo(ctx);
        }
    }
    
    // Draw message
    drawMessage(ctx, message) {
        ctx.save();
        
        ctx.font = '16px "Press Start 2P"';
        ctx.fillStyle = message.color;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        // Add shadow for readability
        ctx.shadowColor = '#000000';
        ctx.shadowBlur = 4;
        ctx.shadowOffsetX = 2;
        ctx.shadowOffsetY = 2;
        
        ctx.fillText(
            message.text,
            ctx.canvas.width / 2,
            ctx.canvas.height / 2
        );
        
        ctx.restore();
    }
    
    // Draw point display
    drawPointDisplay(ctx, display) {
        ctx.save();
        
        ctx.font = '12px "Press Start 2P"';
        ctx.fillStyle = display.color;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.globalAlpha = display.timer / 1000;
        
        ctx.fillText(
            display.points.toString(),
            display.x,
            display.y + display.offsetY
        );
        
        ctx.restore();
    }
    
    // Draw fruit indicator
    drawFruitIndicator(ctx) {
        const sprite = assetManager.getSprite(this.currentFruit);
        if (sprite) {
            // Draw in bottom right corner
            const x = ctx.canvas.width - 30;
            const y = ctx.canvas.height - 30;
            
            // Blink if timer is low
            if (this.fruitTimer > 2000 || Math.floor(this.fruitTimer / 200) % 2 === 0) {
                ctx.drawImage(sprite, x, y);
            }
        }
    }
    
    // Draw debug information
    drawDebugInfo(ctx) {
        ctx.save();
        
        ctx.font = '10px monospace';
        ctx.fillStyle = '#00ff00';
        ctx.textAlign = 'left';
        
        const debugInfo = [
            `State: ${this.gameStates.getState()}`,
            `Score: ${this.gameStates.score}`,
            `Lives: ${this.gameStates.lives}`,
            `Level: ${this.gameStates.level}`,
            `Dots: ${this.gameStates.dotsCollected}/${this.gameStates.totalDots}`
        ];
        
        debugInfo.forEach((info, index) => {
            ctx.fillText(info, 10, 40 + index * 12);
        });
        
        ctx.restore();
    }
    
    // Show ready message
    showReady() {
        this.showMessage('READY!', 2000, '#ffff00');
    }
    
    // Show game over
    showGameOver() {
        this.flashScreen('#ff0000', 500);
    }
    
    // Show level complete
    showLevelComplete() {
        this.showMessage(`LEVEL ${this.gameStates.level} COMPLETE!`, 2000, '#00ff00');
        this.flashScreen('#00ff00', 300);
    }
    
    // Show extra life
    showExtraLife() {
        this.showMessage('EXTRA LIFE!', 1500, '#00ffff');
        this.flashScreen('#00ffff', 200);
    }
    
    // Clear all UI elements
    clear() {
        this.messageQueue = [];
        this.currentMessage = null;
        this.pointDisplays = [];
        this.flashTimer = 0;
        this.currentFruit = null;
        this.fruitTimer = 0;
    }
    
    // Set direction input handler
    setDirectionHandler(handler) {
        this.onDirectionInput = handler;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UI;
}