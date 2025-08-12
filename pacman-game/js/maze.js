class Maze {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.tileSize = 20;
        this.rows = 31;
        this.cols = 28;
        
        this.WALL = '#';
        this.DOT = '.';
        this.POWER_PELLET = 'o';
        this.EMPTY = ' ';
        this.GHOST_HOUSE = 'H';
        this.TUNNEL = 'T';
        
        this.dotsRemaining = 0;
        this.totalDots = 0;
        
        this.layout = this.createClassicMaze();
        this.initializeMaze();
    }
    
    createClassicMaze() {
        return [
            '############################',
            '#............##............#',
            '#.####.#####.##.#####.####.#',
            '#o####.#####.##.#####.####o#',
            '#.####.#####.##.#####.####.#',
            '#..........................#',
            '#.####.##.########.##.####.#',
            '#.####.##.########.##.####.#',
            '#......##....##....##......#',
            '######.##### ## #####.######',
            '######.##### ## #####.######',
            '######.##          ##.######',
            '######.## ###HH### ##.######',
            '######.## #HHHHHH# ##.######',
            'T     .   #HHHHHH#   .     T',
            '######.## #HHHHHH# ##.######',
            '######.## ######## ##.######',
            '######.##          ##.######',
            '######.## ######## ##.######',
            '######.## ######## ##.######',
            '#............##............#',
            '#.####.#####.##.#####.####.#',
            '#.####.#####.##.#####.####.#',
            '#o..##................##..o#',
            '###.##.##.########.##.##.###',
            '###.##.##.########.##.##.###',
            '#......##....##....##......#',
            '#.##########.##.##########.#',
            '#.##########.##.##########.#',
            '#..........................#',
            '############################'
        ].map(row => row.split(''));
    }
    
    initializeMaze() {
        this.dotsRemaining = 0;
        this.totalDots = 0;
        
        for (let row = 0; row < this.rows; row++) {
            for (let col = 0; col < this.cols; col++) {
                const tile = this.layout[row][col];
                if (tile === this.DOT) {
                    this.dotsRemaining++;
                    this.totalDots++;
                } else if (tile === this.POWER_PELLET) {
                    this.dotsRemaining++;
                    this.totalDots++;
                }
            }
        }
    }
    
    render() {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        for (let row = 0; row < this.rows; row++) {
            for (let col = 0; col < this.cols; col++) {
                const x = col * this.tileSize;
                const y = row * this.tileSize;
                const tile = this.layout[row][col];
                
                switch(tile) {
                    case this.WALL:
                        this.drawWall(x, y);
                        break;
                    case this.DOT:
                        this.drawDot(x, y);
                        break;
                    case this.POWER_PELLET:
                        this.drawPowerPellet(x, y);
                        break;
                    case this.GHOST_HOUSE:
                        this.drawGhostHouse(x, y);
                        break;
                }
            }
        }
    }
    
    drawWall(x, y) {
        this.ctx.fillStyle = '#0033ff';
        this.ctx.fillRect(x + 2, y + 2, this.tileSize - 4, this.tileSize - 4);
        
        this.ctx.strokeStyle = '#0066ff';
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(x + 2, y + 2, this.tileSize - 4, this.tileSize - 4);
    }
    
    drawDot(x, y) {
        this.ctx.fillStyle = '#ffffff';
        this.ctx.beginPath();
        this.ctx.arc(x + this.tileSize/2, y + this.tileSize/2, 2, 0, Math.PI * 2);
        this.ctx.fill();
    }
    
    drawPowerPellet(x, y) {
        const time = Date.now() / 200;
        const pulse = Math.sin(time) * 0.5 + 0.5;
        const radius = 6 + pulse * 2;
        
        this.ctx.fillStyle = '#ffffff';
        this.ctx.beginPath();
        this.ctx.arc(x + this.tileSize/2, y + this.tileSize/2, radius, 0, Math.PI * 2);
        this.ctx.fill();
    }
    
    drawGhostHouse(x, y) {
        this.ctx.fillStyle = '#ff00ff';
        this.ctx.fillRect(x + 4, y + 4, this.tileSize - 8, this.tileSize - 8);
        
        this.ctx.strokeStyle = '#ff66ff';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(x + 4, y + 4, this.tileSize - 8, this.tileSize - 8);
    }
    
    getTile(x, y) {
        const col = Math.floor(x / this.tileSize);
        const row = Math.floor(y / this.tileSize);
        
        if (row < 0 || row >= this.rows || col < 0 || col >= this.cols) {
            return this.WALL;
        }
        
        return this.layout[row][col];
    }
    
    setTile(x, y, value) {
        const col = Math.floor(x / this.tileSize);
        const row = Math.floor(y / this.tileSize);
        
        if (row >= 0 && row < this.rows && col >= 0 && col < this.cols) {
            this.layout[row][col] = value;
        }
    }
    
    isWall(x, y) {
        const tile = this.getTile(x, y);
        return tile === this.WALL;
    }
    
    isTunnel(x, y) {
        const col = Math.floor(x / this.tileSize);
        const row = Math.floor(y / this.tileSize);
        
        return (col <= 0 || col >= this.cols - 1) && this.layout[row] && this.layout[row][col] === this.TUNNEL;
    }
    
    getTunnelExit(x, y) {
        const col = Math.floor(x / this.tileSize);
        const row = Math.floor(y / this.tileSize);
        
        if (col <= 0) {
            return { x: (this.cols - 2) * this.tileSize, y: y };
        } else if (col >= this.cols - 1) {
            return { x: this.tileSize, y: y };
        }
        
        return { x, y };
    }
    
    collectDot(x, y) {
        const tile = this.getTile(x, y);
        
        if (tile === this.DOT) {
            this.setTile(x, y, this.EMPTY);
            this.dotsRemaining--;
            return { type: 'dot', points: 10 };
        } else if (tile === this.POWER_PELLET) {
            this.setTile(x, y, this.EMPTY);
            this.dotsRemaining--;
            return { type: 'power', points: 50 };
        }
        
        return null;
    }
    
    isValidPosition(x, y) {
        const tile = this.getTile(x, y);
        return tile !== this.WALL && tile !== this.GHOST_HOUSE;
    }
    
    getValidMoves(x, y) {
        const moves = [];
        const col = Math.floor(x / this.tileSize);
        const row = Math.floor(y / this.tileSize);
        
        const directions = [
            { dx: 0, dy: -1, dir: 'up' },
            { dx: 0, dy: 1, dir: 'down' },
            { dx: -1, dy: 0, dir: 'left' },
            { dx: 1, dy: 0, dir: 'right' }
        ];
        
        for (const { dx, dy, dir } of directions) {
            const newCol = col + dx;
            const newRow = row + dy;
            const newX = newCol * this.tileSize;
            const newY = newRow * this.tileSize;
            
            if (this.isValidPosition(newX, newY) || this.isTunnel(newX, newY)) {
                moves.push({ x: newX, y: newY, direction: dir });
            }
        }
        
        return moves;
    }
    
    getGhostHouseCenter() {
        return {
            x: 14 * this.tileSize,
            y: 14 * this.tileSize
        };
    }
    
    getGhostHouseEntrance() {
        return {
            x: 14 * this.tileSize,
            y: 11 * this.tileSize
        };
    }
    
    isLevelComplete() {
        return this.dotsRemaining === 0;
    }
    
    resetLevel() {
        this.layout = this.createClassicMaze();
        this.initializeMaze();
    }
}

export default Maze;