# Pac-Man Arcade Game

A classic arcade-style Pac-Man game built with HTML5 Canvas and JavaScript, featuring authentic 8-bit aesthetics, intelligent ghost AI, and smooth gameplay.

## Installation & Setup

### Prerequisites and Dependencies
- Modern web browser (Chrome, Firefox, Safari, or Edge)
- Python 3.x or Node.js (for local server)
- No additional dependencies required - pure vanilla JavaScript

### How to Download/Clone the Game
```bash
# Clone the repository
git clone [repository-url]
cd pacman-game

# Or download the ZIP file and extract it
```

### Running Locally

#### Option 1: Python HTTP Server
```bash
# Python 3
python -m http.server 8000

# Python 2
python -m SimpleHTTPServer 8000

# Open browser to http://localhost:8000
```

#### Option 2: Node.js Live Server
```bash
# Install live-server globally
npm install -g live-server

# Run in project directory
live-server

# Automatically opens in default browser
```

#### Option 3: VS Code Live Server Extension
1. Install "Live Server" extension in VS Code
2. Right-click on `index.html`
3. Select "Open with Live Server"

### Browser Compatibility Notes
- **Chrome 90+**: Full support, optimal performance
- **Firefox 88+**: Full support
- **Safari 14+**: Full support
- **Edge 90+**: Full support
- **Mobile browsers**: Touch controls supported on modern mobile browsers

## How to Play

### Game Controls
- **Arrow Keys**: Move Pac-Man (↑ ↓ ← →)
- **WASD Keys**: Alternative movement controls
  - W: Move up
  - A: Move left
  - S: Move down
  - D: Move right
- **Space Bar**: Pause/Resume game
- **Enter**: Start new game
- **M**: Mute/Unmute sound

### Objective and Win Conditions
- **Primary Goal**: Clear all dots and power pellets from the maze
- **Avoid**: Getting caught by ghosts (unless powered up)
- **Level Completion**: Collect all dots to advance to the next level
- **Game Over**: Lose all lives (default: 3 lives)

### Scoring System Explanation
| Item | Points | Description |
|------|--------|-------------|
| Dot | 10 | Regular pellets scattered throughout the maze |
| Power Pellet | 50 | Large flashing pellets in corners |
| Ghost (1st) | 200 | First ghost eaten after power-up |
| Ghost (2nd) | 400 | Second ghost in same power-up |
| Ghost (3rd) | 800 | Third ghost in same power-up |
| Ghost (4th) | 1600 | Fourth ghost in same power-up |
| Cherry | 100 | Bonus fruit (Level 1) |
| Strawberry | 300 | Bonus fruit (Level 2) |
| Orange | 500 | Bonus fruit (Level 3-4) |
| Apple | 700 | Bonus fruit (Level 5-6) |
| Melon | 1000 | Bonus fruit (Level 7-8) |
| Galaxian | 2000 | Bonus item (Level 9-10) |
| Bell | 3000 | Bonus item (Level 11-12) |
| Key | 5000 | Bonus item (Level 13+) |

### Ghost Behaviors and Strategies

#### Ghost Personalities
1. **Blinky (Red)**: The aggressive shadow
   - Always chases Pac-Man directly
   - Speed increases as dots are collected
   - Most dangerous in open areas

2. **Pinky (Pink)**: The ambusher
   - Targets 4 tiles ahead of Pac-Man's direction
   - Excellent at cutting off escape routes
   - Watch for pincer movements with Blinky

3. **Inky (Cyan)**: The unpredictable one
   - Uses complex targeting based on Blinky's position
   - Movement appears random but is calculated
   - Hardest to predict

4. **Clyde (Orange)**: The lazy one
   - Chases when far, retreats when close
   - Targets Pac-Man when > 8 tiles away
   - Returns to corner when nearby

#### Ghost Mode Cycles
- **Chase Mode**: Ghosts actively pursue based on their AI
- **Scatter Mode**: Ghosts retreat to corners (7 seconds)
- **Frightened Mode**: Blue/vulnerable after power pellet
- **Returning Mode**: Eyes returning to ghost house after eaten

### Power-Up Mechanics
- **Duration**: 8 seconds (decreases in higher levels)
- **Visual Cues**: 
  - Ghosts turn blue when vulnerable
  - Flash white/blue when power-up is ending (last 2 seconds)
- **Strategy Tips**:
  - Chain ghost captures for maximum points
  - Use power-ups to clear difficult maze sections
  - Save power pellets for emergencies in later levels

### Level Progression
- **Level 1-2**: Normal speed, 8-second power-ups
- **Level 3-4**: Slightly faster ghosts, 7-second power-ups
- **Level 5-6**: Faster ghosts, 6-second power-ups
- **Level 7-10**: Very fast ghosts, 5-second power-ups
- **Level 11-15**: Maximum ghost speed, 4-second power-ups
- **Level 16+**: Extreme difficulty, 3-second power-ups

## Customization Guide

### Modifying Maze Layouts

Edit the maze array in `js/maze.js`:
```javascript
createClassicMaze() {
    return [
        '############################',
        '#............##............#',
        // Modify these strings to change layout
        // # = Wall
        // . = Dot
        // o = Power Pellet
        // H = Ghost House
        // T = Tunnel
        // (space) = Empty
    ];
}
```

### Adjusting Difficulty Settings

In `js/game.js`, modify these constants:
```javascript
const DIFFICULTY_SETTINGS = {
    easy: {
        ghostSpeed: 0.8,
        playerSpeed: 1.0,
        powerUpDuration: 10000,
        scatterDuration: 7000
    },
    normal: {
        ghostSpeed: 1.0,
        playerSpeed: 1.0,
        powerUpDuration: 8000,
        scatterDuration: 5000
    },
    hard: {
        ghostSpeed: 1.2,
        playerSpeed: 1.0,
        powerUpDuration: 5000,
        scatterDuration: 3000
    }
};
```

### Changing Ghost AI Parameters

Modify ghost behaviors in `js/ghost.js`:
```javascript
// Adjust chase aggressiveness
this.chaseSpeed = 1.0;  // Increase for harder difficulty

// Modify targeting offsets
this.targetOffset = 4;  // Tiles ahead for Pinky

// Change scatter corners
this.scatterTarget = { x: 0, y: 0 };  // Top-left corner
```

### Customizing Sprites and Colors

In `js/renderer.js` or CSS:
```css
:root {
    --maze-wall-color: #0033ff;
    --dot-color: #ffffff;
    --pacman-color: #ffff00;
    --blinky-color: #ff0000;
    --pinky-color: #ffb8ff;
    --inky-color: #00ffff;
    --clyde-color: #ffb851;
}
```

### Adding New Sound Effects

In `js/sounds.js`:
```javascript
const sounds = {
    chomp: 'sounds/chomp.wav',
    death: 'sounds/death.wav',
    eatGhost: 'sounds/eat-ghost.wav',
    // Add new sounds here
    levelComplete: 'sounds/level-complete.wav',
    extraLife: 'sounds/extra-life.wav'
};
```

### Creating Custom Levels

Add level definitions in `js/levels.js`:
```javascript
const customLevel = {
    maze: [/* maze array */],
    dotCount: 240,
    ghostSpeed: 1.1,
    bonusFruit: 'cherry',
    powerUpDuration: 7000
};
```

## Code Structure

### File Organization Overview
```
pacman-game/
├── index.html              # Main game page
├── css/
│   └── style.css          # Game styling and animations
├── js/
│   ├── game.js            # Main game controller
│   ├── player.js          # Pac-Man logic
│   ├── ghost.js           # Ghost AI and behavior
│   ├── maze.js            # Maze generation and collision
│   ├── powerup.js         # Power-up system
│   ├── renderer.js        # Canvas rendering engine
│   ├── input.js           # Keyboard/touch controls
│   ├── sounds.js          # Audio management
│   └── utils.js           # Helper functions
├── sounds/                 # Audio files
├── images/                 # Sprite sheets
└── GAME_README.md         # This file
```

### Key Classes

#### Game Class
Main game loop and state management:
- `init()`: Initialize game components
- `update(deltaTime)`: Update game logic
- `render()`: Draw game state
- `handleCollisions()`: Check player/ghost collisions
- `nextLevel()`: Progress to next level

#### Player Class
Pac-Man character control:
- `move(direction)`: Handle movement input
- `update(deltaTime)`: Update position
- `checkWallCollision()`: Prevent wall clipping
- `animate()`: Chomping animation

#### Ghost Class
Individual ghost AI:
- `calculateTarget()`: Determine chase target
- `findPath()`: Pathfinding logic
- `updateState()`: Mode transitions
- `makeVulnerable()`: Power-up effect
- `returnToHouse()`: After being eaten

#### Maze Class
Level structure and collision:
- `createMaze()`: Generate maze layout
- `getTile(x, y)`: Get tile at position
- `isWall(x, y)`: Collision detection
- `collectDot(x, y)`: Handle dot collection

### Game Loop Explanation
```javascript
function gameLoop(timestamp) {
    const deltaTime = timestamp - lastTime;
    
    // 1. Process input
    handleInput();
    
    // 2. Update game state
    updatePlayer(deltaTime);
    updateGhosts(deltaTime);
    updatePowerUps(deltaTime);
    
    // 3. Check collisions
    checkDotCollection();
    checkGhostCollisions();
    checkBonusItems();
    
    // 4. Render frame
    clearCanvas();
    renderMaze();
    renderItems();
    renderPlayer();
    renderGhosts();
    renderUI();
    
    // 5. Schedule next frame
    requestAnimationFrame(gameLoop);
}
```

### AI Algorithm Details

#### A* Pathfinding
Ghosts use A* algorithm for navigation:
```javascript
function findPath(start, target) {
    const openSet = [start];
    const closedSet = [];
    
    while (openSet.length > 0) {
        // Find node with lowest f score
        // f = g (distance from start) + h (heuristic to target)
        const current = getLowestFScore(openSet);
        
        if (current === target) {
            return reconstructPath(current);
        }
        
        // Explore neighbors
        for (const neighbor of getNeighbors(current)) {
            // Calculate scores and update path
        }
    }
}
```

#### Ghost Decision Trees
```
Chase Mode:
├── Calculate target based on personality
├── Find shortest path to target
└── Move toward next tile in path

Scatter Mode:
├── Set corner as target
├── Find path to corner
└── Patrol corner area

Frightened Mode:
├── Choose random valid direction
├── Avoid Pac-Man
└── Move at reduced speed
```

### Collision Detection System
```javascript
// Tile-based collision
function checkCollision(entity1, entity2) {
    const distance = Math.sqrt(
        Math.pow(entity1.x - entity2.x, 2) +
        Math.pow(entity1.y - entity2.y, 2)
    );
    
    return distance < (entity1.radius + entity2.radius);
}

// Wall collision using tile map
function isWallCollision(x, y, width, height) {
    const corners = [
        { x: x, y: y },                    // Top-left
        { x: x + width, y: y },           // Top-right
        { x: x, y: y + height },           // Bottom-left
        { x: x + width, y: y + height }   // Bottom-right
    ];
    
    return corners.some(corner => maze.isWall(corner.x, corner.y));
}
```

## Enhancement Ideas

### Add Two-Player Mode
- Split-screen competitive mode
- Cooperative mode with shared lives
- Turn-based gameplay option
- Local multiplayer via keyboard sharing

### Create Online Leaderboards
- Global high score tracking
- Daily/weekly/monthly challenges
- Player profiles and statistics
- Achievement badges and rewards

### Implement Save States
- Save game progress to localStorage
- Multiple save slots
- Cloud save synchronization
- Resume from exact game state

### Add New Ghost Types
- **Shadow Ghost**: Teleports randomly
- **Speed Ghost**: Varies speed unpredictably
- **Mirror Ghost**: Copies player movements
- **Hunter Ghost**: Tracks player's trail

### Create Bonus Stages
- Fruit collection mini-games
- Time attack challenges
- Ghost-free speed runs
- Maze puzzle variations

### Mobile Touch Controls
- Virtual D-pad overlay
- Swipe gesture controls
- Tilt controls using accelerometer
- Haptic feedback support

### Level Editor Tool
- Visual maze designer
- Drag-and-drop tile placement
- Test mode within editor
- Share custom levels online
- Import/export level codes

### Multiplayer Networking
- WebRTC peer-to-peer connections
- Lobby system for matchmaking
- Spectator mode
- Tournament brackets

### Achievement System
- "Perfect Clear" - Complete level without losing a life
- "Ghost Hunter" - Eat all 4 ghosts in one power-up
- "Speed Runner" - Complete level under time limit
- "Pacifist" - Complete level eating minimal ghosts
- "Cherry Picker" - Collect all bonus fruits
- "Survivor" - Reach level 20
- "Perfect Game" - Complete game without dying

### Custom Maze Generator
- Procedural maze generation
- Difficulty-based complexity
- Themed maze styles (castle, space, underwater)
- Symmetric and asymmetric options
- Adjustable maze size

## Troubleshooting

### Common Issues and Fixes

#### Game Won't Start
- **Check browser console** for JavaScript errors (F12)
- **Clear browser cache**: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
- **Verify file structure**: Ensure all files are in correct directories
- **Check browser compatibility**: Update to latest version

#### No Sound
- **Browser autoplay policy**: Click anywhere on page to enable sound
- **Check volume**: Ensure browser tab isn't muted
- **Audio files missing**: Verify sounds/ directory exists
- **Format issues**: Use .wav or .mp3 formats

#### Laggy Performance
- **Close other tabs**: Free up browser resources
- **Disable extensions**: Ad blockers may interfere
- **Lower quality settings**: Reduce particle effects
- **Check CPU usage**: Close unnecessary applications

#### Controls Not Responding
- **Click game canvas**: Ensure game has focus
- **Check keyboard layout**: Some layouts may not support WASD
- **Disable browser shortcuts**: Conflicting key bindings
- **Try different browser**: Test in Chrome/Firefox

### Performance Optimization Tips

#### Rendering Optimization
```javascript
// Use requestAnimationFrame
requestAnimationFrame(gameLoop);

// Implement dirty rectangles
if (needsRedraw) {
    ctx.clearRect(dirtyRect);
    renderDirtyArea(dirtyRect);
}

// Cache static elements
const mazeCanvas = document.createElement('canvas');
renderMazeOnce(mazeCanvas);
```

#### Memory Management
```javascript
// Object pooling for particles
const particlePool = [];
function getParticle() {
    return particlePool.pop() || new Particle();
}

// Clear references
ghost.target = null;
delete unusedObjects;
```

#### Network Optimization
- Compress assets (images, sounds)
- Use sprite sheets instead of individual images
- Lazy load non-critical resources
- Implement progressive loading

### Debug Mode Instructions

Enable debug mode by adding `?debug=true` to URL:
```
http://localhost:8000/index.html?debug=true
```

Debug features:
- **F1**: Show FPS counter
- **F2**: Display collision boxes
- **F3**: Show ghost AI targets
- **F4**: Display pathfinding grid
- **F5**: Instant win level
- **F6**: Add extra life
- **F7**: Toggle invincibility
- **F8**: Slow motion mode

### Console Commands
Open browser console (F12) and use:
```javascript
// Skip to specific level
game.skipToLevel(5);

// Give extra lives
game.player.lives = 99;

// Infinite power-up
game.powerUpDuration = Infinity;

// Change game speed
game.speed = 0.5;  // Half speed
game.speed = 2.0;  // Double speed

// Spawn bonus fruit
game.spawnBonus('cherry');

// Toggle ghost AI
game.ghostsEnabled = false;
```

## Credits and License

This Pac-Man clone is created for educational purposes. Pac-Man is a trademark of Bandai Namco Entertainment Inc.

### Technologies Used
- HTML5 Canvas API
- Vanilla JavaScript ES6+
- CSS3 Animations
- Web Audio API
- Local Storage API

### Resources
- Original Pac-Man design by Toru Iwatani
- Ghost AI inspired by Pac-Man Dossier by Jamey Pittman
- Sound effects created with sfxr
- Sprite artwork recreated in pixel art style

---

For questions, bug reports, or contributions, please visit the project repository.