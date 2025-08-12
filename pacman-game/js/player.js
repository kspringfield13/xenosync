class Player {
    constructor(tileSize) {
        this.tileSize = tileSize;
        this.gridX = 13;
        this.gridY = 23;
        this.x = this.gridX * tileSize + tileSize / 2;
        this.y = this.gridY * tileSize + tileSize / 2;
        this.targetX = this.x;
        this.targetY = this.y;
        this.speed = 2;
        this.direction = 'right';
        this.nextDirection = null;
        this.animationFrame = 0;
        this.animationTimer = 0;
        this.mouthOpen = true;
        this.isAlive = true;
        this.deathAnimationFrame = 0;
        this.lives = 3;
        this.score = 0;
        this.dotsEaten = 0;
        this.powerMode = false;
        this.powerTimer = 0;
        this.respawnTimer = 0;
        this.movementQueue = [];
        this.interpolationProgress = 0;
    }

    update(maze, deltaTime) {
        if (!this.isAlive) {
            this.updateDeathAnimation(deltaTime);
            return;
        }

        if (this.respawnTimer > 0) {
            this.respawnTimer -= deltaTime;
            if (this.respawnTimer <= 0) {
                this.respawn();
            }
            return;
        }

        this.updatePowerMode(deltaTime);
        this.updateAnimation(deltaTime);
        this.processMovementQueue();
        this.move(maze);
        this.checkCollisions(maze);
    }

    move(maze) {
        const movingHorizontally = this.direction === 'left' || this.direction === 'right';
        const movingVertically = this.direction === 'up' || this.direction === 'down';

        if (this.nextDirection && this.canTurn(maze, this.nextDirection)) {
            if ((movingHorizontally && this.isAlignedVertically()) ||
                (movingVertically && this.isAlignedHorizontally())) {
                this.direction = this.nextDirection;
                this.nextDirection = null;
                this.updateTarget();
            }
        }

        const atTarget = Math.abs(this.x - this.targetX) < 1 && Math.abs(this.y - this.targetY) < 1;
        
        if (atTarget) {
            this.x = this.targetX;
            this.y = this.targetY;
            this.gridX = Math.round(this.x / this.tileSize - 0.5);
            this.gridY = Math.round(this.y / this.tileSize - 0.5);

            if (this.canMove(maze, this.direction)) {
                this.updateTarget();
            }
        } else {
            const dx = this.targetX - this.x;
            const dy = this.targetY - this.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance > 0) {
                this.x += (dx / distance) * this.speed;
                this.y += (dy / distance) * this.speed;
            }
        }

        this.handleTunnels(maze);
    }

    updateTarget() {
        switch (this.direction) {
            case 'left':
                this.targetX = (this.gridX - 1) * this.tileSize + this.tileSize / 2;
                break;
            case 'right':
                this.targetX = (this.gridX + 1) * this.tileSize + this.tileSize / 2;
                break;
            case 'up':
                this.targetY = (this.gridY - 1) * this.tileSize + this.tileSize / 2;
                break;
            case 'down':
                this.targetY = (this.gridY + 1) * this.tileSize + this.tileSize / 2;
                break;
        }
    }

    canMove(maze, direction) {
        let nextX = this.gridX;
        let nextY = this.gridY;

        switch (direction) {
            case 'left': nextX--; break;
            case 'right': nextX++; break;
            case 'up': nextY--; break;
            case 'down': nextY++; break;
        }

        if (nextX < 0 || nextX >= maze[0].length || nextY < 0 || nextY >= maze.length) {
            return this.isTunnel(nextX, nextY, maze);
        }

        return maze[nextY][nextX] !== 1;
    }

    canTurn(maze, direction) {
        return this.canMove(maze, direction);
    }

    isAlignedHorizontally() {
        return Math.abs(this.x - (this.gridX * this.tileSize + this.tileSize / 2)) < 2;
    }

    isAlignedVertically() {
        return Math.abs(this.y - (this.gridY * this.tileSize + this.tileSize / 2)) < 2;
    }

    handleTunnels(maze) {
        if (this.gridX < 0) {
            this.gridX = maze[0].length - 1;
            this.x = this.gridX * this.tileSize + this.tileSize / 2;
            this.targetX = this.x;
        } else if (this.gridX >= maze[0].length) {
            this.gridX = 0;
            this.x = this.tileSize / 2;
            this.targetX = this.x;
        }
    }

    isTunnel(x, y, maze) {
        const tunnelY = 14;
        return y === tunnelY && (x < 0 || x >= maze[0].length);
    }

    checkCollisions(maze) {
        const tile = maze[this.gridY][this.gridX];
        
        if (tile === 2) {
            maze[this.gridY][this.gridX] = 0;
            this.score += 10;
            this.dotsEaten++;
        } else if (tile === 3) {
            maze[this.gridY][this.gridX] = 0;
            this.score += 50;
            this.activatePowerMode();
        }
    }

    activatePowerMode() {
        this.powerMode = true;
        this.powerTimer = 8000;
    }

    updatePowerMode(deltaTime) {
        if (this.powerMode) {
            this.powerTimer -= deltaTime;
            if (this.powerTimer <= 0) {
                this.powerMode = false;
            }
        }
    }

    updateAnimation(deltaTime) {
        this.animationTimer += deltaTime;
        if (this.animationTimer > 50) {
            this.animationTimer = 0;
            this.animationFrame = (this.animationFrame + 1) % 4;
            this.mouthOpen = this.animationFrame < 2;
        }
    }

    updateDeathAnimation(deltaTime) {
        if (this.deathAnimationFrame < 12) {
            this.deathAnimationFrame += deltaTime * 0.01;
            if (this.deathAnimationFrame >= 12) {
                this.respawnTimer = 1000;
            }
        }
    }

    processMovementQueue() {
        if (this.movementQueue.length > 0) {
            this.nextDirection = this.movementQueue[0];
            if (this.canTurn(maze, this.nextDirection)) {
                this.movementQueue.shift();
            }
        }
    }

    setDirection(direction) {
        const oppositeDirections = {
            'left': 'right',
            'right': 'left',
            'up': 'down',
            'down': 'up'
        };

        if (oppositeDirections[this.direction] === direction) {
            this.direction = direction;
            this.updateTarget();
            this.nextDirection = null;
            this.movementQueue = [];
        } else {
            this.nextDirection = direction;
            if (this.movementQueue.length < 2) {
                this.movementQueue.push(direction);
            }
        }
    }

    die() {
        if (this.isAlive) {
            this.isAlive = false;
            this.deathAnimationFrame = 0;
            this.lives--;
        }
    }

    respawn() {
        this.isAlive = true;
        this.gridX = 13;
        this.gridY = 23;
        this.x = this.gridX * this.tileSize + this.tileSize / 2;
        this.y = this.gridY * this.tileSize + this.tileSize / 2;
        this.targetX = this.x;
        this.targetY = this.y;
        this.direction = 'right';
        this.nextDirection = null;
        this.deathAnimationFrame = 0;
        this.powerMode = false;
        this.powerTimer = 0;
        this.movementQueue = [];
    }

    draw(ctx) {
        ctx.save();
        ctx.translate(this.x, this.y);

        if (!this.isAlive) {
            this.drawDeathAnimation(ctx);
        } else {
            this.drawPacman(ctx);
        }

        ctx.restore();
    }

    drawPacman(ctx) {
        const size = this.tileSize * 0.8;
        ctx.fillStyle = '#FFFF00';

        if (this.mouthOpen) {
            let startAngle, endAngle;
            switch (this.direction) {
                case 'right':
                    startAngle = 0.2 * Math.PI;
                    endAngle = 1.8 * Math.PI;
                    break;
                case 'left':
                    startAngle = 1.2 * Math.PI;
                    endAngle = 0.8 * Math.PI;
                    break;
                case 'up':
                    startAngle = 1.7 * Math.PI;
                    endAngle = 1.3 * Math.PI;
                    break;
                case 'down':
                    startAngle = 0.7 * Math.PI;
                    endAngle = 0.3 * Math.PI;
                    break;
            }
            
            ctx.beginPath();
            ctx.arc(0, 0, size / 2, startAngle, endAngle);
            ctx.lineTo(0, 0);
            ctx.closePath();
            ctx.fill();
        } else {
            ctx.beginPath();
            ctx.arc(0, 0, size / 2, 0, 2 * Math.PI);
            ctx.fill();
        }
    }

    drawDeathAnimation(ctx) {
        const size = this.tileSize * 0.8;
        ctx.fillStyle = '#FFFF00';
        
        const angle = (this.deathAnimationFrame / 12) * Math.PI;
        ctx.beginPath();
        ctx.arc(0, 0, size / 2, angle, 2 * Math.PI - angle);
        ctx.lineTo(0, 0);
        ctx.closePath();
        ctx.fill();
    }
}

export default Player;