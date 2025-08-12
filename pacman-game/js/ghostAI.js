class GhostAI {
    constructor(maze) {
        this.maze = maze;
        this.ghosts = {};
        this.globalModeTimer = 0;
        this.currentWave = 0;
        this.wavePattern = this.getWavePattern();
        
        // Initialize ghosts
        this.initializeGhosts();
    }
    
    // Initialize all ghosts
    initializeGhosts() {
        const ghostConfigs = GameConfig.GHOST_CONFIG;
        
        this.ghosts.blinky = new Ghost('Blinky', ghostConfigs.blinky, this.maze);
        this.ghosts.pinky = new Ghost('Pinky', ghostConfigs.pinky, this.maze);
        this.ghosts.inky = new Ghost('Inky', ghostConfigs.inky, this.maze);
        this.ghosts.clyde = new Ghost('Clyde', ghostConfigs.clyde, this.maze);
        
        this.ghostArray = Object.values(this.ghosts);
    }
    
    // Get wave pattern for mode switching
    getWavePattern() {
        // Classic Pac-Man wave pattern (scatter/chase durations)
        return [
            { mode: 'scatter', duration: 7000 },
            { mode: 'chase', duration: 20000 },
            { mode: 'scatter', duration: 7000 },
            { mode: 'chase', duration: 20000 },
            { mode: 'scatter', duration: 5000 },
            { mode: 'chase', duration: 20000 },
            { mode: 'scatter', duration: 5000 },
            { mode: 'chase', duration: Infinity } // Permanent chase
        ];
    }
    
    // Update all ghosts
    update(deltaTime, pacman, level = 1) {
        // Update global mode timer
        this.updateGlobalMode(deltaTime);
        
        // Update each ghost
        this.ghostArray.forEach(ghost => {
            // Apply level-based speed modifier
            const speedModifier = this.getSpeedModifier(level);
            ghost.speed = GameConfig.GHOST_SPEED * speedModifier;
            
            // Update ghost (Inky needs Blinky's position)
            if (ghost.name === 'Inky') {
                ghost.update(deltaTime, pacman, this.ghosts.blinky);
            } else {
                ghost.update(deltaTime, pacman);
            }
        });
        
        // Check for collisions
        this.checkCollisions(pacman);
    }
    
    // Update global mode for all ghosts
    updateGlobalMode(deltaTime) {
        if (this.currentWave < this.wavePattern.length) {
            this.globalModeTimer += deltaTime;
            
            const currentPattern = this.wavePattern[this.currentWave];
            
            if (this.globalModeTimer >= currentPattern.duration) {
                this.globalModeTimer = 0;
                this.currentWave++;
                
                if (this.currentWave < this.wavePattern.length) {
                    const nextPattern = this.wavePattern[this.currentWave];
                    this.setAllGhostsMode(nextPattern.mode);
                }
            }
        }
    }
    
    // Set mode for all ghosts
    setAllGhostsMode(mode) {
        this.ghostArray.forEach(ghost => {
            if (ghost.mode !== 'eaten' && ghost.mode !== 'frightened') {
                ghost.setMode(mode);
            }
        });
    }
    
    // Make all ghosts frightened
    makeAllFrightened() {
        this.ghostArray.forEach(ghost => {
            ghost.makeFrightened();
        });
    }
    
    // Get speed modifier based on level
    getSpeedModifier(level) {
        // Increase speed by 5% per level, max 150%
        return Math.min(1 + (level - 1) * 0.05, 1.5);
    }
    
    // Check collisions with Pac-Man
    checkCollisions(pacman) {
        const pacmanGrid = {
            x: Math.floor((pacman.x + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE),
            y: Math.floor((pacman.y + GameConfig.TILE_SIZE / 2) / GameConfig.TILE_SIZE)
        };
        
        for (const ghost of this.ghostArray) {
            // Check if ghost and Pac-Man are on same tile
            if (ghost.gridX === pacmanGrid.x && ghost.gridY === pacmanGrid.y) {
                // Check pixel-perfect collision
                const distance = Math.sqrt(
                    Math.pow(ghost.x - pacman.x, 2) + 
                    Math.pow(ghost.y - pacman.y, 2)
                );
                
                if (distance < GameConfig.TILE_SIZE * 0.8) {
                    if (ghost.mode === 'frightened') {
                        // Pac-Man eats ghost
                        if (ghost.eat()) {
                            return { type: 'eatGhost', ghost: ghost };
                        }
                    } else if (ghost.mode !== 'eaten') {
                        // Ghost catches Pac-Man
                        return { type: 'death' };
                    }
                }
            }
        }
        
        return null;
    }
    
    // Reset all ghosts
    reset() {
        this.ghostArray.forEach(ghost => ghost.reset());
        this.globalModeTimer = 0;
        this.currentWave = 0;
    }
    
    // Reset for new level
    resetForNewLevel() {
        this.ghostArray.forEach(ghost => {
            ghost.reset();
            // Adjust release timers for higher levels
            ghost.releaseTimer = Math.max(ghost.getReleaseTiming() * 0.8, 0);
        });
        this.globalModeTimer = 0;
        this.currentWave = 0;
    }
    
    // Draw all ghosts
    draw(ctx) {
        this.ghostArray.forEach(ghost => ghost.draw(ctx));
    }
    
    // Get ghost by name
    getGhost(name) {
        return this.ghosts[name.toLowerCase()];
    }
    
    // Get all ghosts
    getAllGhosts() {
        return this.ghostArray;
    }
    
    // Debug: Draw ghost targets
    drawDebugInfo(ctx) {
        if (window.DEBUG_MODE) {
            ctx.save();
            
            this.ghostArray.forEach(ghost => {
                // Draw target tile
                if (ghost.targetTile) {
                    ctx.fillStyle = ghost.color + '44';
                    ctx.fillRect(
                        ghost.targetTile.x * GameConfig.TILE_SIZE,
                        ghost.targetTile.y * GameConfig.TILE_SIZE,
                        GameConfig.TILE_SIZE,
                        GameConfig.TILE_SIZE
                    );
                }
                
                // Draw ghost info
                ctx.fillStyle = ghost.color;
                ctx.font = '8px monospace';
                ctx.fillText(
                    `${ghost.name}: ${ghost.mode}`,
                    ghost.x,
                    ghost.y - 5
                );
            });
            
            ctx.restore();
        }
    }
    
    // A* Pathfinding for smarter ghost movement (optional enhancement)
    findPath(startX, startY, targetX, targetY) {
        const openSet = [];
        const closedSet = [];
        const path = [];
        
        const start = {
            x: startX,
            y: startY,
            g: 0,
            h: this.heuristic(startX, startY, targetX, targetY),
            f: 0,
            parent: null
        };
        
        start.f = start.g + start.h;
        openSet.push(start);
        
        while (openSet.length > 0) {
            // Find node with lowest f score
            let current = openSet[0];
            let currentIndex = 0;
            
            for (let i = 1; i < openSet.length; i++) {
                if (openSet[i].f < current.f) {
                    current = openSet[i];
                    currentIndex = i;
                }
            }
            
            // Remove current from open set
            openSet.splice(currentIndex, 1);
            closedSet.push(current);
            
            // Check if we reached the target
            if (current.x === targetX && current.y === targetY) {
                let temp = current;
                while (temp.parent) {
                    path.push({ x: temp.x, y: temp.y });
                    temp = temp.parent;
                }
                return path.reverse();
            }
            
            // Check neighbors
            const neighbors = [
                { x: 0, y: -1 }, // Up
                { x: 1, y: 0 },  // Right
                { x: 0, y: 1 },  // Down
                { x: -1, y: 0 }  // Left
            ];
            
            for (const dir of neighbors) {
                const neighborX = current.x + dir.x;
                const neighborY = current.y + dir.y;
                
                // Check if neighbor is walkable
                if (!this.isWalkable(neighborX, neighborY)) {
                    continue;
                }
                
                // Check if neighbor is in closed set
                if (closedSet.find(n => n.x === neighborX && n.y === neighborY)) {
                    continue;
                }
                
                const g = current.g + 1;
                const h = this.heuristic(neighborX, neighborY, targetX, targetY);
                const f = g + h;
                
                // Check if neighbor is in open set
                let neighbor = openSet.find(n => n.x === neighborX && n.y === neighborY);
                
                if (!neighbor) {
                    neighbor = {
                        x: neighborX,
                        y: neighborY,
                        g: g,
                        h: h,
                        f: f,
                        parent: current
                    };
                    openSet.push(neighbor);
                } else if (g < neighbor.g) {
                    neighbor.g = g;
                    neighbor.f = f;
                    neighbor.parent = current;
                }
            }
        }
        
        return []; // No path found
    }
    
    // Heuristic function for A*
    heuristic(x1, y1, x2, y2) {
        // Manhattan distance
        return Math.abs(x2 - x1) + Math.abs(y2 - y1);
    }
    
    // Check if tile is walkable
    isWalkable(x, y) {
        if (x < 0 || x >= GameConfig.GRID_WIDTH || 
            y < 0 || y >= GameConfig.GRID_HEIGHT) {
            return false;
        }
        
        const tile = this.maze[y][x];
        return tile !== 0; // 0 is wall
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GhostAI;
}