class GameLoop {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.ctx.imageSmoothingEnabled = false;
        
        this.running = false;
        this.paused = false;
        this.lastTime = 0;
        this.deltaTime = 0;
        this.accumulator = 0;
        this.fixedTimeStep = 1000 / 60; // 60 FPS
        
        this.updateCallback = null;
        this.renderCallback = null;
        
        // Performance monitoring
        this.fps = 60;
        this.frameCount = 0;
        this.lastFpsUpdate = 0;
        
        // Bind the main loop
        this.loop = this.loop.bind(this);
    }
    
    // Set update callback
    setUpdateCallback(callback) {
        this.updateCallback = callback;
    }
    
    // Set render callback
    setRenderCallback(callback) {
        this.renderCallback = callback;
    }
    
    // Start the game loop
    start() {
        if (!this.running) {
            this.running = true;
            this.lastTime = performance.now();
            this.lastFpsUpdate = this.lastTime;
            requestAnimationFrame(this.loop);
        }
    }
    
    // Stop the game loop
    stop() {
        this.running = false;
    }
    
    // Pause the game loop
    pause() {
        this.paused = true;
    }
    
    // Resume the game loop
    resume() {
        this.paused = false;
        this.lastTime = performance.now();
    }
    
    // Toggle pause state
    togglePause() {
        if (this.paused) {
            this.resume();
        } else {
            this.pause();
        }
    }
    
    // Main game loop
    loop(currentTime) {
        if (!this.running) return;
        
        // Calculate delta time
        this.deltaTime = currentTime - this.lastTime;
        this.lastTime = currentTime;
        
        // Cap delta time to prevent spiral of death
        this.deltaTime = Math.min(this.deltaTime, 250);
        
        // Update FPS counter
        this.updateFPS(currentTime);
        
        if (!this.paused) {
            // Accumulate time for fixed timestep
            this.accumulator += this.deltaTime;
            
            // Fixed timestep update
            while (this.accumulator >= this.fixedTimeStep) {
                if (this.updateCallback) {
                    this.updateCallback(this.fixedTimeStep);
                }
                this.accumulator -= this.fixedTimeStep;
            }
        }
        
        // Render (always render even when paused for UI updates)
        if (this.renderCallback) {
            // Interpolation value for smooth rendering
            const interpolation = this.accumulator / this.fixedTimeStep;
            this.renderCallback(this.ctx, interpolation);
        }
        
        // Draw FPS counter
        this.drawFPS();
        
        // Continue the loop
        requestAnimationFrame(this.loop);
    }
    
    // Update FPS calculation
    updateFPS(currentTime) {
        this.frameCount++;
        
        if (currentTime - this.lastFpsUpdate >= 1000) {
            this.fps = this.frameCount;
            this.frameCount = 0;
            this.lastFpsUpdate = currentTime;
        }
    }
    
    // Draw FPS counter (optional, for debugging)
    drawFPS() {
        if (window.DEBUG_MODE) {
            this.ctx.save();
            this.ctx.fillStyle = '#00ff00';
            this.ctx.font = '10px "Press Start 2P"';
            this.ctx.fillText(`FPS: ${this.fps}`, 10, 20);
            this.ctx.restore();
        }
    }
    
    // Clear the canvas
    clear() {
        this.ctx.fillStyle = GameConfig.COLORS.background;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }
    
    // Helper method to draw grid (for debugging)
    drawGrid() {
        if (window.DEBUG_MODE) {
            this.ctx.save();
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
            this.ctx.lineWidth = 1;
            
            // Draw vertical lines
            for (let x = 0; x <= GameConfig.GRID_WIDTH; x++) {
                this.ctx.beginPath();
                this.ctx.moveTo(x * GameConfig.TILE_SIZE, 0);
                this.ctx.lineTo(x * GameConfig.TILE_SIZE, this.canvas.height);
                this.ctx.stroke();
            }
            
            // Draw horizontal lines
            for (let y = 0; y <= GameConfig.GRID_HEIGHT; y++) {
                this.ctx.beginPath();
                this.ctx.moveTo(0, y * GameConfig.TILE_SIZE);
                this.ctx.lineTo(this.canvas.width, y * GameConfig.TILE_SIZE);
                this.ctx.stroke();
            }
            
            this.ctx.restore();
        }
    }
    
    // Check if the game is running
    isRunning() {
        return this.running;
    }
    
    // Check if the game is paused
    isPaused() {
        return this.paused;
    }
    
    // Get current FPS
    getFPS() {
        return this.fps;
    }
    
    // Reset the game loop
    reset() {
        this.stop();
        this.paused = false;
        this.lastTime = 0;
        this.deltaTime = 0;
        this.accumulator = 0;
        this.frameCount = 0;
        this.fps = 60;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GameLoop;
}