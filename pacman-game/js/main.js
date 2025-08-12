// Main game controller
class PacManGame {
    constructor() {
        this.canvas = document.getElementById('gameCanvas');
        this.ctx = this.canvas.getContext('2d');
        
        // Core systems
        this.gameLoop = null;
        this.gameStates = null;
        this.ui = null;
        this.ghostAI = null;
        
        // Game entities
        this.pacman = null;
        this.maze = null;
        this.fruits = [];
        
        // Initialize game
        this.initialize();
    }
    
    // Initialize game systems
    async initialize() {
        try {
            // Load assets
            await assetManager.loadAll();
            
            // Initialize game systems
            this.gameLoop = new GameLoop(this.canvas);
            this.gameStates = new GameStates();
            this.ui = new UI(this.gameStates);
            
            // Initialize maze
            this.initializeMaze();
            
            // Initialize ghost AI
            this.ghostAI = new GhostAI(this.maze);
            
            // Initialize Pac-Man
            this.initializePacMan();
            
            // Set up game loop callbacks
            this.gameLoop.setUpdateCallback((deltaTime) => this.update(deltaTime));
            this.gameLoop.setRenderCallback((ctx, interpolation) => this.render(ctx, interpolation));
            
            // Set up UI callbacks
            this.ui.setDirectionHandler((direction) => this.handleDirectionInput(direction));
            
            // Set up game state callbacks
            this.gameStates.onStateChange = (newState, oldState) => this.handleStateChange(newState, oldState);
            
            // Count total dots
            this.countDots();
            
            // Start game loop
            this.gameLoop.start();
            
            // Show start screen
            this.gameStates.setState('START_SCREEN');
            
        } catch (error) {
            console.error('Failed to initialize game:', error);
        }
    }
    
    // Initialize maze
    initializeMaze() {
        this.maze = JSON.parse(JSON.stringify(GameConfig.MAZE_TEMPLATE));
    }
    
    // Initialize Pac-Man
    initializePacMan() {
        this.pacman = {
            x: 14 * GameConfig.TILE_SIZE,
            y: 23 * GameConfig.TILE_SIZE,
            gridX: 14,
            gridY: 23,
            direction: { x: -1, y: 0 },
            nextDirection: null,
            speed: GameConfig.PLAYER_SPEED,
            animationFrame: 0,
            animationTimer: 0,
            mouthOpen: true,
            powered: false,
            powerTimer: 0
        };
    }
    
    // Count total dots in maze
    countDots() {
        let count = 0;
        for (let y = 0; y < this.maze.length; y++) {
            for (let x = 0; x < this.maze[y].length; x++) {
                if (this.maze[y][x] === 1 || this.maze[y][x] === 2) {
                    count++;
                }
            }
        }
        this.gameStates.totalDots = count;
    }
    
    // Main update loop
    update(deltaTime) {
        // Update game states
        this.gameStates.update(deltaTime);
        
        // Update UI
        this.ui.update(deltaTime);
        
        // Only update game entities when playing
        if (this.gameStates.isPlayable()) {
            // Update Pac-Man
            this.updatePacMan(deltaTime);
            
            // Update ghosts
            this.ghostAI.update(deltaTime, this.pacman, this.gameStates.level);
            
            // Check collisions
            this.checkCollisions();
            
            // Update fruits
            this.updateFruits(deltaTime);
            
            // Spawn fruit if needed
            this.checkFruitSpawn();
        }
    }
    
    // Update Pac-Man
    updatePacMan(deltaTime) {
        // Update animation
        this.pacman.animationTimer += deltaTime;
        if (this.pacman.animationTimer > 50) {
            this.pacman.mouthOpen = !this.pacman.mouthOpen;
            this.pacman.animationTimer = 0;
        }
        
        // Update power mode
        if (this.pacman.powered) {
            this.pacman.powerTimer -= deltaTime;
            if (this.pacman.powerTimer <= 0) {
                this.pacman.powered = false;
                this.pacman.speed = GameConfig.PLAYER_SPEED;
            }
        }
        
        // Check for direction change
        if (this.pacman.nextDirection) {
            const nextX = this.pacman.gridX + this.pacman.nextDirection.x;
            const nextY = this.pacman.gridY + this.pacman.nextDirection.y;
            
            if (this.canMoveTo(nextX, nextY)) {
                this.pacman.direction = this.pacman.nextDirection;
                this.pacman.nextDirection = null;
            }
        }
        
        // Move Pac-Man
        const moveDistance = (this.pacman.speed * deltaTime) / 1000 * GameConfig.TILE_SIZE;
        const newX = this.pacman.x + this.pacman.direction.x * moveDistance;
        const newY = this.pacman.y + this.pacman.direction.y * moveDistance;
        
        // Check if can move
        const checkX = Math.floor((newX + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE);
        const checkY = Math.floor((newY + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE);
        
        if (this.canMoveTo(checkX, checkY)) {
            this.pacman.x = newX;
            this.pacman.y = newY;
            
            // Handle tunnel wrapping
            if (this.pacman.x < -GameConfig.TILE_SIZE) {
                this.pacman.x = GameConfig.CANVAS_WIDTH;
            } else if (this.pacman.x > GameConfig.CANVAS_WIDTH) {
                this.pacman.x = -GameConfig.TILE_SIZE;
            }
            
            // Update grid position
            this.pacman.gridX = Math.floor((this.pacman.x + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE);
            this.pacman.gridY = Math.floor((this.pacman.y + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE);
            
            // Check for dot collection
            this.checkDotCollection();
        }
    }
    
    // Check if can move to position
    canMoveTo(x, y) {
        // Check bounds
        if (x < 0 || x >= GameConfig.GRID_WIDTH || 
            y < 0 || y >= GameConfig.GRID_HEIGHT) {
            // Allow tunnel movement
            if (y === 14 && (x < 0 || x >= GameConfig.GRID_WIDTH)) {
                return true;
            }
            return false;
        }
        
        // Check if tile is walkable
        const tile = this.maze[y][x];
        return tile !== 0; // 0 is wall
    }
    
    // Check dot collection
    checkDotCollection() {
        const tile = this.maze[this.pacman.gridY][this.pacman.gridX];
        
        if (tile === 1) {
            // Regular dot
            this.maze[this.pacman.gridY][this.pacman.gridX] = 3; // Empty
            this.gameStates.collectDot();
        } else if (tile === 2) {
            // Power pellet
            this.maze[this.pacman.gridY][this.pacman.gridX] = 3; // Empty
            this.gameStates.collectPowerPellet();
            this.activatePowerMode();
        }
    }
    
    // Activate power mode
    activatePowerMode() {
        this.pacman.powered = true;
        this.pacman.powerTimer = GameConfig.POWER_PELLET_DURATION;
        this.pacman.speed = GameConfig.PLAYER_POWERED_SPEED;
        
        // Make all ghosts frightened
        this.ghostAI.makeAllFrightened();
    }
    
    // Check collisions
    checkCollisions() {
        // Check ghost collisions
        const collision = this.ghostAI.checkCollisions(this.pacman);
        
        if (collision) {
            if (collision.type === 'eatGhost') {
                // Pac-Man ate a ghost
                const points = this.gameStates.eatGhost();
                this.ui.showPoints(
                    collision.ghost.x + GameConfig.TILE_SIZE / 2,
                    collision.ghost.y + GameConfig.TILE_SIZE / 2,
                    points,
                    '#00ffff'
                );
            } else if (collision.type === 'death') {
                // Ghost caught Pac-Man
                this.handleDeath();
            }
        }
        
        // Check fruit collisions
        this.checkFruitCollisions();
    }
    
    // Handle Pac-Man death
    handleDeath() {
        this.gameStates.setState('DEATH');
        
        // Reset positions
        this.resetPositions();
    }
    
    // Reset positions
    resetPositions() {
        // Reset Pac-Man
        this.initializePacMan();
        
        // Reset ghosts
        this.ghostAI.reset();
    }
    
    // Update fruits
    updateFruits(deltaTime) {
        this.fruits = this.fruits.filter(fruit => {
            fruit.timer -= deltaTime;
            return fruit.timer > 0;
        });
    }
    
    // Check fruit spawn
    checkFruitSpawn() {
        // Spawn fruit after collecting certain number of dots
        const dotsForFruit = [70, 170];
        
        if (dotsForFruit.includes(this.gameStates.dotsCollected)) {
            this.spawnFruit();
        }
    }
    
    // Spawn fruit
    spawnFruit() {
        const difficulty = GameConfig.DIFFICULTY_LEVELS[Math.min(this.gameStates.level - 1, 11)];
        const fruitType = difficulty.fruitType;
        
        this.fruits.push({
            type: fruitType,
            x: 14 * GameConfig.TILE_SIZE,
            y: 17 * GameConfig.TILE_SIZE,
            timer: 10000 // 10 seconds
        });
        
        this.ui.showFruit(fruitType);
    }
    
    // Check fruit collisions
    checkFruitCollisions() {
        this.fruits = this.fruits.filter(fruit => {
            const distance = Math.sqrt(
                Math.pow(fruit.x - this.pacman.x, 2) + 
                Math.pow(fruit.y - this.pacman.y, 2)
            );
            
            if (distance < GameConfig.TILE_SIZE) {
                // Collect fruit
                const points = this.gameStates.collectFruit(fruit.type);
                this.ui.showPoints(fruit.x, fruit.y, points, '#ff00ff');
                return false;
            }
            
            return true;
        });
    }
    
    // Handle direction input
    handleDirectionInput(direction) {
        const directions = {
            'up': { x: 0, y: -1 },
            'down': { x: 0, y: 1 },
            'left': { x: -1, y: 0 },
            'right': { x: 1, y: 0 }
        };
        
        this.pacman.nextDirection = directions[direction];
    }
    
    // Handle state change
    handleStateChange(newState, oldState) {
        switch(newState) {
            case 'GAME_READY':
                this.resetForNewGame();
                break;
                
            case 'LEVEL_TRANSITION':
                this.resetForNewLevel();
                break;
                
            case 'PAUSED':
                this.gameLoop.pause();
                break;
                
            case 'PLAYING':
                if (oldState === 'PAUSED') {
                    this.gameLoop.resume();
                }
                break;
        }
    }
    
    // Reset for new game
    resetForNewGame() {
        this.initializeMaze();
        this.initializePacMan();
        this.ghostAI.reset();
        this.fruits = [];
        this.countDots();
        this.gameStates.resetForNewLevel();
    }
    
    // Reset for new level
    resetForNewLevel() {
        this.initializeMaze();
        this.initializePacMan();
        this.ghostAI.resetForNewLevel();
        this.fruits = [];
        this.countDots();
        this.gameStates.resetForNewLevel();
    }
    
    // Main render loop
    render(ctx, interpolation) {
        // Clear canvas
        this.gameLoop.clear();
        
        // Draw based on game state
        if (this.gameStates.getState() === 'START_SCREEN') {
            // Draw attract mode
            this.gameStates.drawAttractMode(ctx);
        } else {
            // Draw game
            this.drawGame(ctx);
        }
        
        // Draw UI overlay
        this.ui.draw(ctx);
        
        // Draw debug grid
        this.gameLoop.drawGrid();
    }
    
    // Draw game
    drawGame(ctx) {
        // Draw maze
        this.drawMaze(ctx);
        
        // Draw dots and power pellets
        this.drawDots(ctx);
        
        // Draw fruits
        this.drawFruits(ctx);
        
        // Draw Pac-Man
        this.drawPacMan(ctx);
        
        // Draw ghosts
        this.ghostAI.draw(ctx);
        
        // Draw debug info
        this.ghostAI.drawDebugInfo(ctx);
    }
    
    // Draw maze
    drawMaze(ctx) {
        ctx.strokeStyle = GameConfig.COLORS.wall;
        ctx.lineWidth = 2;
        
        for (let y = 0; y < this.maze.length; y++) {
            for (let x = 0; x < this.maze[y].length; x++) {
                if (this.maze[y][x] === 0) {
                    // Draw wall
                    const wallX = x * GameConfig.TILE_SIZE;
                    const wallY = y * GameConfig.TILE_SIZE;
                    
                    ctx.strokeRect(
                        wallX + 2,
                        wallY + 2,
                        GameConfig.TILE_SIZE - 4,
                        GameConfig.TILE_SIZE - 4
                    );
                }
            }
        }
    }
    
    // Draw dots and power pellets
    drawDots(ctx) {
        for (let y = 0; y < this.maze.length; y++) {
            for (let x = 0; x < this.maze[y].length; x++) {
                const centerX = x * GameConfig.TILE_SIZE + GameConfig.TILE_SIZE / 2;
                const centerY = y * GameConfig.TILE_SIZE + GameConfig.TILE_SIZE / 2;
                
                if (this.maze[y][x] === 1) {
                    // Draw dot
                    ctx.fillStyle = GameConfig.COLORS.dot;
                    ctx.fillRect(centerX - 2, centerY - 2, 4, 4);
                } else if (this.maze[y][x] === 2) {
                    // Draw power pellet
                    ctx.fillStyle = GameConfig.COLORS.powerPellet;
                    ctx.beginPath();
                    ctx.arc(centerX, centerY, 6, 0, Math.PI * 2);
                    ctx.fill();
                }
            }
        }
    }
    
    // Draw fruits
    drawFruits(ctx) {
        this.fruits.forEach(fruit => {
            const sprite = assetManager.getSprite(fruit.type);
            if (sprite) {
                ctx.drawImage(sprite, fruit.x, fruit.y);
            }
        });
    }
    
    // Draw Pac-Man
    drawPacMan(ctx) {
        ctx.save();
        
        const centerX = this.pacman.x + GameConfig.TILE_SIZE / 2;
        const centerY = this.pacman.y + GameConfig.TILE_SIZE / 2;
        
        ctx.fillStyle = this.pacman.powered ? '#ffff00' : GameConfig.COLORS.pacman;
        
        if (this.pacman.mouthOpen) {
            // Draw with mouth open
            ctx.beginPath();
            
            // Determine mouth angle based on direction
            let startAngle = 0.2 * Math.PI;
            let endAngle = 1.8 * Math.PI;
            
            if (this.pacman.direction.x > 0) {
                // Right
                startAngle = 0.2 * Math.PI;
                endAngle = 1.8 * Math.PI;
            } else if (this.pacman.direction.x < 0) {
                // Left
                startAngle = 0.8 * Math.PI;
                endAngle = 0.2 * Math.PI;
            } else if (this.pacman.direction.y < 0) {
                // Up
                startAngle = 1.3 * Math.PI;
                endAngle = 0.7 * Math.PI;
            } else if (this.pacman.direction.y > 0) {
                // Down
                startAngle = 0.3 * Math.PI;
                endAngle = 2.7 * Math.PI;
            }
            
            ctx.arc(centerX, centerY, GameConfig.TILE_SIZE / 2 - 1, startAngle, endAngle);
            ctx.lineTo(centerX, centerY);
            ctx.fill();
        } else {
            // Draw closed (circle)
            ctx.beginPath();
            ctx.arc(centerX, centerY, GameConfig.TILE_SIZE / 2 - 1, 0, Math.PI * 2);
            ctx.fill();
        }
        
        ctx.restore();
    }
}

// Initialize game when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Enable debug mode with query parameter
    if (window.location.search.includes('debug=true')) {
        window.DEBUG_MODE = true;
    }
    
    // Create and start game
    const game = new PacManGame();
    
    // Expose game instance for debugging
    window.game = game;
});