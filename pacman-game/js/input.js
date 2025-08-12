class InputHandler {
    constructor() {
        this.keys = {};
        this.lastKey = null;
        this.keyBuffer = [];
        this.maxBufferSize = 2;
        this.touchStartX = null;
        this.touchStartY = null;
        this.swipeThreshold = 30;
        
        this.setupKeyboardListeners();
        this.setupTouchListeners();
    }

    setupKeyboardListeners() {
        document.addEventListener('keydown', (e) => {
            const key = this.normalizeKey(e.key);
            if (key) {
                e.preventDefault();
                this.keys[key] = true;
                this.lastKey = key;
                this.addToBuffer(key);
            }
        });

        document.addEventListener('keyup', (e) => {
            const key = this.normalizeKey(e.key);
            if (key) {
                e.preventDefault();
                this.keys[key] = false;
            }
        });
    }

    setupTouchListeners() {
        document.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
                const touch = e.touches[0];
                this.touchStartX = touch.clientX;
                this.touchStartY = touch.clientY;
            }
        });

        document.addEventListener('touchmove', (e) => {
            e.preventDefault();
        }, { passive: false });

        document.addEventListener('touchend', (e) => {
            if (this.touchStartX !== null && this.touchStartY !== null) {
                const touch = e.changedTouches[0];
                const deltaX = touch.clientX - this.touchStartX;
                const deltaY = touch.clientY - this.touchStartY;

                if (Math.abs(deltaX) > this.swipeThreshold || Math.abs(deltaY) > this.swipeThreshold) {
                    if (Math.abs(deltaX) > Math.abs(deltaY)) {
                        const direction = deltaX > 0 ? 'right' : 'left';
                        this.lastKey = direction;
                        this.addToBuffer(direction);
                    } else {
                        const direction = deltaY > 0 ? 'down' : 'up';
                        this.lastKey = direction;
                        this.addToBuffer(direction);
                    }
                }

                this.touchStartX = null;
                this.touchStartY = null;
            }
        });
    }

    normalizeKey(key) {
        const keyMap = {
            'ArrowLeft': 'left',
            'ArrowRight': 'right',
            'ArrowUp': 'up',
            'ArrowDown': 'down',
            'a': 'left',
            'A': 'left',
            'd': 'right',
            'D': 'right',
            'w': 'up',
            'W': 'up',
            's': 'down',
            'S': 'down',
            ' ': 'pause',
            'Escape': 'pause',
            'Enter': 'start',
            'p': 'pause',
            'P': 'pause'
        };

        return keyMap[key] || null;
    }

    addToBuffer(key) {
        if (['left', 'right', 'up', 'down'].includes(key)) {
            if (this.keyBuffer.length === 0 || this.keyBuffer[this.keyBuffer.length - 1] !== key) {
                this.keyBuffer.push(key);
                if (this.keyBuffer.length > this.maxBufferSize) {
                    this.keyBuffer.shift();
                }
            }
        }
    }

    getDirection() {
        if (this.keyBuffer.length > 0) {
            return this.keyBuffer[0];
        }

        const directions = ['left', 'right', 'up', 'down'];
        for (let dir of directions) {
            if (this.keys[dir]) {
                return dir;
            }
        }

        return null;
    }

    consumeBufferedDirection() {
        if (this.keyBuffer.length > 0) {
            return this.keyBuffer.shift();
        }
        return null;
    }

    isKeyPressed(key) {
        return this.keys[key] === true;
    }

    clearBuffer() {
        this.keyBuffer = [];
    }

    reset() {
        this.keys = {};
        this.lastKey = null;
        this.keyBuffer = [];
    }
}

export default InputHandler;