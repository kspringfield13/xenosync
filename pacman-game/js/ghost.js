class Ghost {
    constructor(name, config, maze) {
        this.name = name;
        this.color = config.color;
        this.startX = config.startX;
        this.startY = config.startY;
        this.scatterTarget = config.scatterTarget;
        this.personality = config.personality;
        
        // Position (in pixels)
        this.x = this.startX * GameConfig.TILE_SIZE;
        this.y = this.startY * GameConfig.TILE_SIZE;
        
        // Grid position
        this.gridX = this.startX;
        this.gridY = this.startY;
        
        // Movement
        this.speed = GameConfig.GHOST_SPEED;
        this.direction = { x: 0, y: -1 };
        this.nextDirection = null;
        this.targetTile = null;
        
        // State management
        this.mode = 'scatter'; // scatter, chase, frightened, eaten
        this.previousMode = 'scatter';
        this.modeTimer = 0;
        this.inGhostHouse = true;
        this.exitingHouse = false;
        this.dotCounter = 0;
        
        // Animation
        this.animationFrame = 0;
        this.animationTimer = 0;
        
        // Maze reference
        this.maze = maze;
        
        // Path finding
        this.path = [];
        this.pathIndex = 0;
        
        // Release timing (different for each ghost)
        this.releaseTimer = this.getReleaseTiming();
        this.released = false;
    }
    
    // Get release timing based on ghost
    getReleaseTiming() {
        switch(this.name) {
            case 'Blinky': return 0; // Released immediately
            case 'Pinky': return 2000; // 2 seconds
            case 'Inky': return 4000; // 4 seconds
            case 'Clyde': return 6000; // 6 seconds
            default: return 0;
        }
    }
    
    // Update ghost state
    update(deltaTime, pacman, blinky = null) {
        // Update timers
        this.updateTimers(deltaTime);
        
        // Check if ghost should be released
        if (!this.released && this.releaseTimer <= 0) {
            this.released = true;
            this.exitingHouse = true;
        }
        
        // Handle ghost house exit
        if (this.exitingHouse) {
            this.exitGhostHouse();
            return;
        }
        
        // Update animation
        this.updateAnimation(deltaTime);
        
        // Update mode if not eaten
        if (this.mode !== 'eaten') {
            this.updateMode(deltaTime);
        }
        
        // Calculate target based on mode and personality
        this.calculateTarget(pacman, blinky);
        
        // Move towards target
        this.move(deltaTime);
        
        // Check for mode-specific behaviors
        this.handleModeSpecificBehavior();
    }
    
    // Update various timers
    updateTimers(deltaTime) {
        if (this.releaseTimer > 0) {
            this.releaseTimer -= deltaTime;
        }
        
        if (this.modeTimer > 0) {
            this.modeTimer -= deltaTime;
        }
    }
    
    // Update animation frame
    updateAnimation(deltaTime) {
        this.animationTimer += deltaTime;
        if (this.animationTimer > 100) {
            this.animationFrame = (this.animationFrame + 1) % 2;
            this.animationTimer = 0;
        }
    }
    
    // Update ghost mode
    updateMode(deltaTime) {
        if (this.modeTimer <= 0 && this.mode !== 'frightened') {
            // Toggle between scatter and chase
            if (this.mode === 'scatter') {
                this.setMode('chase');
            } else if (this.mode === 'chase') {
                this.setMode('scatter');
            }
        }
    }
    
    // Set ghost mode
    setMode(mode) {
        if (this.mode === 'eaten' && mode !== 'scatter' && mode !== 'chase') {
            return; // Can't change from eaten except back to normal modes
        }
        
        this.previousMode = this.mode;
        this.mode = mode;
        
        switch(mode) {
            case 'scatter':
                this.modeTimer = GameConfig.SCATTER_DURATION;
                this.speed = GameConfig.GHOST_SPEED;
                break;
            case 'chase':
                this.modeTimer = GameConfig.CHASE_DURATION;
                this.speed = GameConfig.GHOST_SPEED;
                break;
            case 'frightened':
                this.modeTimer = GameConfig.POWER_PELLET_DURATION;
                this.speed = GameConfig.GHOST_FRIGHTENED_SPEED;
                this.reverseDirection();
                break;
            case 'eaten':
                this.speed = GameConfig.GHOST_EATEN_SPEED;
                this.targetTile = { x: this.startX, y: this.startY };
                break;
        }
    }
    
    // Calculate target tile based on mode and personality
    calculateTarget(pacman, blinky) {
        if (this.mode === 'eaten') {
            // Return to ghost house
            this.targetTile = { x: this.startX, y: this.startY };
        } else if (this.mode === 'scatter') {
            // Go to corner
            this.targetTile = this.scatterTarget;
        } else if (this.mode === 'frightened') {
            // Random movement
            this.targetTile = this.getRandomTarget();
        } else if (this.mode === 'chase') {
            // Chase based on personality
            this.targetTile = this.getChaseTarget(pacman, blinky);
        }
    }
    
    // Get chase target based on personality
    getChaseTarget(pacman, blinky) {
        const pacmanGrid = {
            x: Math.floor(pacman.x / GameConfig.TILE_SIZE),
            y: Math.floor(pacman.y / GameConfig.TILE_SIZE)
        };
        
        switch(this.personality) {
            case 'aggressive': // Blinky - Direct chase
                return pacmanGrid;
                
            case 'ambush': // Pinky - Target 4 tiles ahead of Pac-Man
                const ahead = 4;
                return {
                    x: pacmanGrid.x + (pacman.direction.x * ahead),
                    y: pacmanGrid.y + (pacman.direction.y * ahead)
                };
                
            case 'random': // Inky - Complex targeting using Blinky
                if (blinky) {
                    const blinkyGrid = {
                        x: Math.floor(blinky.x / GameConfig.TILE_SIZE),
                        y: Math.floor(blinky.y / GameConfig.TILE_SIZE)
                    };
                    const targetAhead = {
                        x: pacmanGrid.x + (pacman.direction.x * 2),
                        y: pacmanGrid.y + (pacman.direction.y * 2)
                    };
                    return {
                        x: targetAhead.x + (targetAhead.x - blinkyGrid.x),
                        y: targetAhead.y + (targetAhead.y - blinkyGrid.y)
                    };
                }
                return pacmanGrid;
                
            case 'coward': // Clyde - Chase when far, flee when close
                const distance = Math.sqrt(
                    Math.pow(this.gridX - pacmanGrid.x, 2) + 
                    Math.pow(this.gridY - pacmanGrid.y, 2)
                );
                
                if (distance > 8) {
                    return pacmanGrid; // Chase when far
                } else {
                    return this.scatterTarget; // Flee to corner when close
                }
                
            default:
                return pacmanGrid;
        }
    }
    
    // Get random target for frightened mode
    getRandomTarget() {
        const possibleTargets = [];
        const directions = [
            { x: 0, y: -1 }, // Up
            { x: 1, y: 0 },  // Right
            { x: 0, y: 1 },  // Down
            { x: -1, y: 0 }  // Left
        ];
        
        directions.forEach(dir => {
            const newX = this.gridX + dir.x;
            const newY = this.gridY + dir.y;
            
            if (this.canMoveTo(newX, newY)) {
                possibleTargets.push({ x: newX, y: newY });
            }
        });
        
        if (possibleTargets.length > 0) {
            return possibleTargets[Math.floor(Math.random() * possibleTargets.length)];
        }
        
        return { x: this.gridX, y: this.gridY };
    }
    
    // Move ghost
    move(deltaTime) {
        if (!this.targetTile) return;
        
        // Calculate next move
        const nextMove = this.calculateNextMove();
        
        if (nextMove) {
            // Update direction
            this.direction = nextMove;
            
            // Calculate speed (slower in tunnel)
            let currentSpeed = this.speed;
            if (this.isInTunnel()) {
                currentSpeed = GameConfig.GHOST_TUNNEL_SPEED;
            }
            
            // Move ghost
            const moveDistance = (currentSpeed * deltaTime) / 1000 * GameConfig.TILE_SIZE;
            this.x += this.direction.x * moveDistance;
            this.y += this.direction.y * moveDistance;
            
            // Handle tunnel wrapping
            this.handleTunnelWrap();
            
            // Update grid position
            this.gridX = Math.floor((this.x + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE);
            this.gridY = Math.floor((this.y + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE);
        }
    }
    
    // Calculate next move towards target
    calculateNextMove() {
        const possibleMoves = [];
        const directions = [
            { x: 0, y: -1 }, // Up
            { x: 1, y: 0 },  // Right
            { x: 0, y: 1 },  // Down
            { x: -1, y: 0 }  // Left
        ];
        
        // Can't reverse direction (except when frightened)
        const reverseDir = { x: -this.direction.x, y: -this.direction.y };
        
        directions.forEach(dir => {
            // Skip reverse direction unless frightened
            if (this.mode !== 'frightened' && 
                dir.x === reverseDir.x && dir.y === reverseDir.y) {
                return;
            }
            
            const newX = this.gridX + dir.x;
            const newY = this.gridY + dir.y;
            
            if (this.canMoveTo(newX, newY)) {
                const distance = this.getDistance(newX, newY, this.targetTile.x, this.targetTile.y);
                possibleMoves.push({ direction: dir, distance: distance });
            }
        });
        
        // Sort by distance and return best move
        if (possibleMoves.length > 0) {
            possibleMoves.sort((a, b) => a.distance - b.distance);
            return possibleMoves[0].direction;
        }
        
        return null;
    }
    
    // Check if ghost can move to tile
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
    
    // Get distance between two points
    getDistance(x1, y1, x2, y2) {
        return Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
    }
    
    // Check if ghost is in tunnel
    isInTunnel() {
        return this.gridY === 14 && (this.gridX < 6 || this.gridX > 21);
    }
    
    // Handle tunnel wrapping
    handleTunnelWrap() {
        if (this.x < -GameConfig.TILE_SIZE) {
            this.x = GameConfig.CANVAS_WIDTH;
        } else if (this.x > GameConfig.CANVAS_WIDTH) {
            this.x = -GameConfig.TILE_SIZE;
        }
    }
    
    // Reverse ghost direction
    reverseDirection() {
        this.direction = { x: -this.direction.x, y: -this.direction.y };
    }
    
    // Exit ghost house
    exitGhostHouse() {
        const exitX = 14;
        const exitY = 11;
        const targetX = exitX * GameConfig.TILE_SIZE;
        const targetY = exitY * GameConfig.TILE_SIZE;
        
        // Move to center of ghost house
        if (Math.abs(this.x - targetX) > 2) {
            this.x += this.x < targetX ? 1 : -1;
        } else {
            this.x = targetX;
        }
        
        // Move up to exit
        if (this.x === targetX && this.y > targetY) {
            this.y -= 1;
        }
        
        // Check if exited
        if (this.y <= targetY) {
            this.exitingHouse = false;
            this.inGhostHouse = false;
            this.gridX = exitX;
            this.gridY = exitY;
            this.y = targetY;
        }
    }
    
    // Handle mode-specific behavior
    handleModeSpecificBehavior() {
        if (this.mode === 'eaten' && 
            this.gridX === this.startX && this.gridY === this.startY) {
            // Ghost has returned to house, resurrect
            this.setMode(this.previousMode === 'frightened' ? 'scatter' : this.previousMode);
            this.inGhostHouse = true;
            this.exitingHouse = true;
        }
    }
    
    // Make ghost frightened
    makeFrightened() {
        if (this.mode !== 'eaten') {
            this.setMode('frightened');
        }
    }
    
    // Eat ghost
    eat() {
        if (this.mode === 'frightened') {
            this.setMode('eaten');
            return true;
        }
        return false;
    }
    
    // Reset ghost to start position
    reset() {
        this.x = this.startX * GameConfig.TILE_SIZE;
        this.y = this.startY * GameConfig.TILE_SIZE;
        this.gridX = this.startX;
        this.gridY = this.startY;
        this.direction = { x: 0, y: -1 };
        this.mode = 'scatter';
        this.inGhostHouse = true;
        this.exitingHouse = false;
        this.released = false;
        this.releaseTimer = this.getReleaseTiming();
        this.modeTimer = GameConfig.SCATTER_DURATION;
    }
    
    // Draw ghost
    draw(ctx) {
        ctx.save();
        
        // Choose sprite based on mode
        let spriteName = this.name.toLowerCase();
        
        if (this.mode === 'frightened') {
            spriteName = 'frightened_ghost';
            // Flash white near end of frightened mode
            if (this.modeTimer < 2000 && Math.floor(this.modeTimer / 200) % 2 === 0) {
                ctx.globalAlpha = 0.5;
            }
        } else if (this.mode === 'eaten') {
            spriteName = 'ghost_eyes';
        }
        
        const sprite = assetManager.getSprite(spriteName);
        if (sprite) {
            ctx.drawImage(sprite, this.x, this.y);
        } else {
            // Fallback rendering
            ctx.fillStyle = this.mode === 'frightened' ? '#0000ff' : this.color;
            ctx.fillRect(this.x, this.y, GameConfig.TILE_SIZE, GameConfig.TILE_SIZE);
        }
        
        ctx.restore();
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Ghost;
}