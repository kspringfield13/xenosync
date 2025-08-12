const GameConfig = {
    // Canvas dimensions (classic Pac-Man is 224x288, we'll double it)
    CANVAS_WIDTH: 448,
    CANVAS_HEIGHT: 496,
    
    // Grid settings
    TILE_SIZE: 16,
    GRID_WIDTH: 28,
    GRID_HEIGHT: 31,
    
    // Game settings
    INITIAL_LIVES: 3,
    POINTS_PER_DOT: 10,
    POINTS_PER_POWER_PELLET: 50,
    POINTS_PER_GHOST: [200, 400, 800, 1600],
    BONUS_FRUIT_POINTS: {
        cherry: 100,
        strawberry: 300,
        orange: 500,
        apple: 700,
        melon: 1000,
        galaxian: 2000,
        bell: 3000,
        key: 5000
    },
    
    // Player settings
    PLAYER_SPEED: 2,
    PLAYER_POWERED_SPEED: 2.5,
    POWER_PELLET_DURATION: 8000, // 8 seconds
    
    // Ghost settings
    GHOST_SPEED: 1.8,
    GHOST_FRIGHTENED_SPEED: 1,
    GHOST_TUNNEL_SPEED: 0.8,
    GHOST_EATEN_SPEED: 4,
    SCATTER_DURATION: 7000,
    CHASE_DURATION: 20000,
    
    // Ghost personalities
    GHOST_CONFIG: {
        blinky: {
            name: 'Blinky',
            color: '#ff0000',
            startX: 14,
            startY: 11,
            scatterTarget: { x: 25, y: 0 },
            personality: 'aggressive'
        },
        pinky: {
            name: 'Pinky',
            color: '#ffb8ff',
            startX: 14,
            startY: 14,
            scatterTarget: { x: 2, y: 0 },
            personality: 'ambush'
        },
        inky: {
            name: 'Inky',
            color: '#00ffff',
            startX: 12,
            startY: 14,
            scatterTarget: { x: 27, y: 31 },
            personality: 'random'
        },
        clyde: {
            name: 'Clyde',
            color: '#ffb851',
            startX: 16,
            startY: 14,
            scatterTarget: { x: 0, y: 31 },
            personality: 'coward'
        }
    },
    
    // Maze layout (simplified representation)
    // 0 = wall, 1 = dot, 2 = power pellet, 3 = empty, 4 = ghost house
    MAZE_TEMPLATE: [
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,1,1,1,1,1,1,1,1,1,1,1,1,0],
        [0,1,0,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,1,0],
        [0,2,0,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,2,0],
        [0,1,0,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,1,0],
        [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
        [0,1,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,1,0],
        [0,1,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,1,0],
        [0,1,1,1,1,1,1,0,0,1,1,1,1,0,0,1,1,1,1,0,0,1,1,1,1,1,1,0],
        [0,0,0,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,1,1,1,1,1,1,1,1,1,1,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,1,0,0,0,4,4,0,0,0,1,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,1,0,4,4,4,4,4,4,0,1,0,0,1,0,0,0,0,0,0],
        [3,3,3,3,3,3,1,1,1,1,0,4,4,4,4,4,4,0,1,1,1,1,3,3,3,3,3,3],
        [0,0,0,0,0,0,1,0,0,1,0,4,4,4,4,4,4,0,1,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,1,1,1,1,1,1,1,1,1,1,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0],
        [0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,1,1,1,1,1,1,1,1,1,1,1,1,0],
        [0,1,0,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,1,0],
        [0,1,0,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,1,0],
        [0,2,1,1,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,1,1,2,0],
        [0,0,0,1,0,0,1,0,0,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,1,0,0,0],
        [0,0,0,1,0,0,1,0,0,1,0,0,0,0,0,0,0,0,1,0,0,1,0,0,1,0,0,0],
        [0,1,1,1,1,1,1,0,0,1,1,1,1,0,0,1,1,1,1,0,0,1,1,1,1,1,1,0],
        [0,1,0,0,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,0,0,0,1,0],
        [0,1,0,0,0,0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,0,0,0,1,0],
        [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
        [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
    ],
    
    // Sound settings
    SOUNDS: {
        startGame: 'sounds/start.wav',
        chomp: 'sounds/chomp.wav',
        eatGhost: 'sounds/eatghost.wav',
        death: 'sounds/death.wav',
        eatFruit: 'sounds/eatfruit.wav',
        powerPellet: 'sounds/power.wav',
        siren: 'sounds/siren.wav',
        retreating: 'sounds/retreating.wav'
    },
    
    // Colors
    COLORS: {
        background: '#000000',
        wall: '#0000ff',
        dot: '#ffb897',
        powerPellet: '#ffb897',
        pacman: '#ffcc00',
        text: '#ffffff',
        frightenedGhost: '#0000ff'
    },
    
    // Difficulty progression
    DIFFICULTY_LEVELS: [
        { level: 1, ghostSpeed: 1.8, playerSpeed: 2, fruitType: 'cherry' },
        { level: 2, ghostSpeed: 1.9, playerSpeed: 2, fruitType: 'strawberry' },
        { level: 3, ghostSpeed: 2.0, playerSpeed: 2, fruitType: 'orange' },
        { level: 4, ghostSpeed: 2.1, playerSpeed: 2, fruitType: 'orange' },
        { level: 5, ghostSpeed: 2.2, playerSpeed: 2, fruitType: 'apple' },
        { level: 6, ghostSpeed: 2.3, playerSpeed: 2, fruitType: 'apple' },
        { level: 7, ghostSpeed: 2.4, playerSpeed: 2, fruitType: 'melon' },
        { level: 8, ghostSpeed: 2.5, playerSpeed: 2, fruitType: 'melon' },
        { level: 9, ghostSpeed: 2.6, playerSpeed: 2, fruitType: 'galaxian' },
        { level: 10, ghostSpeed: 2.7, playerSpeed: 2, fruitType: 'bell' },
        { level: 11, ghostSpeed: 2.8, playerSpeed: 2, fruitType: 'bell' },
        { level: 12, ghostSpeed: 2.9, playerSpeed: 2, fruitType: 'key' }
    ]
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GameConfig;
}