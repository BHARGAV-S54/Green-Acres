document.addEventListener('DOMContentLoaded', () => {
    // Like button toggle
    const likeBtns = document.querySelectorAll('.post-action-btn');
    
    likeBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            if (this.innerText.includes('Helpful')) {
                const icon = this.querySelector('i');
                if (icon.classList.contains('fa-regular')) {
                    icon.classList.remove('fa-regular');
                    icon.classList.add('fa-solid');
                    this.style.color = 'var(--primary-green)';
                } else {
                    icon.classList.remove('fa-solid');
                    icon.classList.add('fa-regular');
                    this.style.color = 'var(--text-muted)';
                }
            }
        });
    });
});
