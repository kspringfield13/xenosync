class AssetManager {
    constructor() {
        this.assets = {
            sprites: {},
            sounds: {},
            fonts: {},
            mazeData: null
        };
        this.loadQueue = [];
        this.loadedCount = 0;
        this.totalAssets = 0;
        this.onLoadComplete = null;
        this.onLoadProgress = null;
    }
    
    // Load all game assets
    async loadAll() {
        return new Promise((resolve, reject) => {
            this.onLoadComplete = resolve;
            
            // Initialize sprite placeholders (we'll draw them programmatically)
            this.createSprites();
            
            // Load sounds
            this.loadSounds();
            
            // Load maze data
            this.loadMazeData();
            
            // Check if all assets are loaded
            this.checkLoadComplete();
        });
    }
    
    // Create sprite placeholders (drawn programmatically for retro feel)
    createSprites() {
        // Create canvas elements for each sprite
        const sprites = [
            'pacman', 'pacman_left', 'pacman_right', 'pacman_up', 'pacman_down',
            'blinky', 'pinky', 'inky', 'clyde',
            'frightened_ghost', 'ghost_eyes',
            'cherry', 'strawberry', 'orange', 'apple', 'melon', 
            'galaxian', 'bell', 'key',
            'dot', 'power_pellet', 'wall_tile'
        ];
        
        sprites.forEach(spriteName => {
            const canvas = document.createElement('canvas');
            canvas.width = 16;
            canvas.height = 16;
            const ctx = canvas.getContext('2d');
            
            // Draw sprites programmatically
            this.drawSprite(ctx, spriteName);
            
            this.assets.sprites[spriteName] = canvas;
        });
    }
    
    // Draw sprites programmatically for authentic retro look
    drawSprite(ctx, spriteName) {
        ctx.imageSmoothingEnabled = false;
        
        switch(spriteName) {
            case 'pacman':
            case 'pacman_right':
                ctx.fillStyle = '#ffcc00';
                ctx.beginPath();
                ctx.arc(8, 8, 7, 0.2 * Math.PI, 1.8 * Math.PI);
                ctx.lineTo(8, 8);
                ctx.fill();
                break;
                
            case 'pacman_left':
                ctx.fillStyle = '#ffcc00';
                ctx.beginPath();
                ctx.arc(8, 8, 7, 0.8 * Math.PI, 0.2 * Math.PI);
                ctx.lineTo(8, 8);
                ctx.fill();
                break;
                
            case 'pacman_up':
                ctx.fillStyle = '#ffcc00';
                ctx.beginPath();
                ctx.arc(8, 8, 7, 1.3 * Math.PI, 0.7 * Math.PI);
                ctx.lineTo(8, 8);
                ctx.fill();
                break;
                
            case 'pacman_down':
                ctx.fillStyle = '#ffcc00';
                ctx.beginPath();
                ctx.arc(8, 8, 7, 0.3 * Math.PI, 2.7 * Math.PI);
                ctx.lineTo(8, 8);
                ctx.fill();
                break;
                
            case 'blinky':
                this.drawGhost(ctx, '#ff0000');
                break;
                
            case 'pinky':
                this.drawGhost(ctx, '#ffb8ff');
                break;
                
            case 'inky':
                this.drawGhost(ctx, '#00ffff');
                break;
                
            case 'clyde':
                this.drawGhost(ctx, '#ffb851');
                break;
                
            case 'frightened_ghost':
                this.drawGhost(ctx, '#0000ff');
                break;
                
            case 'ghost_eyes':
                // Draw just the eyes
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(3, 5, 3, 4);
                ctx.fillRect(10, 5, 3, 4);
                ctx.fillStyle = '#0000ff';
                ctx.fillRect(4, 6, 2, 2);
                ctx.fillRect(11, 6, 2, 2);
                break;
                
            case 'dot':
                ctx.fillStyle = '#ffb897';
                ctx.fillRect(7, 7, 2, 2);
                break;
                
            case 'power_pellet':
                ctx.fillStyle = '#ffb897';
                ctx.beginPath();
                ctx.arc(8, 8, 4, 0, 2 * Math.PI);
                ctx.fill();
                break;
                
            case 'wall_tile':
                ctx.strokeStyle = '#0000ff';
                ctx.lineWidth = 2;
                ctx.strokeRect(1, 1, 14, 14);
                break;
                
            case 'cherry':
                ctx.fillStyle = '#ff0000';
                ctx.beginPath();
                ctx.arc(5, 10, 3, 0, 2 * Math.PI);
                ctx.arc(11, 10, 3, 0, 2 * Math.PI);
                ctx.fill();
                ctx.strokeStyle = '#00ff00';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(8, 5);
                ctx.lineTo(5, 7);
                ctx.moveTo(8, 5);
                ctx.lineTo(11, 7);
                ctx.stroke();
                break;
                
            case 'strawberry':
                ctx.fillStyle = '#ff0066';
                ctx.beginPath();
                ctx.moveTo(8, 12);
                ctx.quadraticCurveTo(4, 8, 4, 6);
                ctx.quadraticCurveTo(4, 4, 8, 4);
                ctx.quadraticCurveTo(12, 4, 12, 6);
                ctx.quadraticCurveTo(12, 8, 8, 12);
                ctx.fill();
                ctx.fillStyle = '#00ff00';
                ctx.fillRect(7, 2, 2, 3);
                break;
                
            case 'orange':
                ctx.fillStyle = '#ff8800';
                ctx.beginPath();
                ctx.arc(8, 8, 5, 0, 2 * Math.PI);
                ctx.fill();
                break;
                
            case 'apple':
                ctx.fillStyle = '#ff0000';
                ctx.beginPath();
                ctx.arc(8, 9, 5, 0, 2 * Math.PI);
                ctx.fill();
                ctx.fillStyle = '#00ff00';
                ctx.fillRect(7, 3, 2, 3);
                break;
                
            case 'melon':
                ctx.fillStyle = '#00ff00';
                ctx.beginPath();
                ctx.ellipse(8, 8, 6, 4, 0, 0, 2 * Math.PI);
                ctx.fill();
                ctx.strokeStyle = '#008800';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(2, 8);
                ctx.lineTo(14, 8);
                ctx.stroke();
                break;
                
            default:
                // Default square for undefined sprites
                ctx.fillStyle = '#ff00ff';
                ctx.fillRect(4, 4, 8, 8);
                break;
        }
    }
    
    // Draw a ghost shape
    drawGhost(ctx, color) {
        ctx.fillStyle = color;
        // Head
        ctx.beginPath();
        ctx.arc(8, 8, 6, Math.PI, 0);
        ctx.closePath();
        ctx.fill();
        // Body
        ctx.fillRect(2, 8, 12, 5);
        // Wavy bottom
        ctx.beginPath();
        ctx.moveTo(2, 13);
        ctx.lineTo(2, 15);
        ctx.lineTo(5, 13);
        ctx.lineTo(8, 15);
        ctx.lineTo(11, 13);
        ctx.lineTo(14, 15);
        ctx.lineTo(14, 13);
        ctx.fill();
        
        // Eyes
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(4, 6, 3, 3);
        ctx.fillRect(9, 6, 3, 3);
        ctx.fillStyle = '#0000ff';
        ctx.fillRect(5, 7, 2, 2);
        ctx.fillRect(10, 7, 2, 2);
    }
    
    // Load sound effects
    loadSounds() {
        const soundList = Object.entries(GameConfig.SOUNDS);
        
        soundList.forEach(([name, path]) => {
            const audio = new Audio();
            audio.preload = 'auto';
            
            // Create placeholder audio for now
            this.assets.sounds[name] = audio;
            
            // In a real implementation, you would load actual sound files
            // audio.src = path;
            // audio.addEventListener('canplaythrough', () => this.assetLoaded());
        });
    }
    
    // Load maze data
    loadMazeData() {
        this.assets.mazeData = GameConfig.MAZE_TEMPLATE;
    }
    
    // Check if all assets are loaded
    checkLoadComplete() {
        // Since we're creating assets programmatically, they're ready immediately
        if (this.onLoadComplete) {
            this.onLoadComplete(this.assets);
        }
    }
    
    // Get a specific asset
    getSprite(name) {
        return this.assets.sprites[name];
    }
    
    getSound(name) {
        return this.assets.sounds[name];
    }
    
    getMazeData() {
        return this.assets.mazeData;
    }
    
    // Play a sound effect
    playSound(name, loop = false) {
        const sound = this.assets.sounds[name];
        if (sound && sound.src) {
            sound.loop = loop;
            sound.currentTime = 0;
            sound.play().catch(e => {
                // Handle autoplay restrictions
                console.log('Sound play prevented:', e);
            });
        }
    }
    
    // Stop a sound effect
    stopSound(name) {
        const sound = this.assets.sounds[name];
        if (sound) {
            sound.pause();
            sound.currentTime = 0;
        }
    }
    
    // Stop all sounds
    stopAllSounds() {
        Object.values(this.assets.sounds).forEach(sound => {
            if (sound) {
                sound.pause();
                sound.currentTime = 0;
            }
        });
    }
}

// Create global asset manager instance
const assetManager = new AssetManager();