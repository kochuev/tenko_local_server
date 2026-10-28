jQuery(document).ready(function () {
    console.log(window.location.pathname.split("/").pop())
    if(jQuery(window).width() <= 1920){
        resize();
    }else{
        if(window.location.pathname.split("/").pop() === 'login'){
            jQuery('.main').addClass('main--full login');
        }else{
            jQuery('.main').addClass('main--full dashboard');
        }
    }

    openMenu(); 
    
    jQuery(".eye-icon").click(function () {
        jQuery(this).toggleClass("visible");
        var input = jQuery(this).closest('.form-group').find('input')
        if (jQuery(this).hasClass('visible')) {
            input.attr("type", "text");
        } else {
            input.attr("type", "password");
        }
    });
});
function resize() {
    jQuery(window).on('resize', function () {
        var ww = jQuery(window).width();
        var wh = jQuery('body').height();
        var pageScale = ww / 1920;
        var scaleHeight = wh * pageScale;

        if (jQuery(window).width() > 900) {
            jQuery('.main, .modal-content').css('transform', 'scale(' + pageScale + ')');
            jQuery('.main').height(scaleHeight);
            jQuery('.sidebar').prependTo('.main');
            
        } else {
            jQuery('.main, .modal-content').css({ 'transform': 'scale(' + 1 + ')', 'height': 'auto', });
            jQuery('.sidebar').appendTo('.mobile-menu');

        }
    });
    jQuery(window).trigger('resize');
}

function openMenu() {
    jQuery('.hamburger-menu').on('click', function () {
        jQuery('body').toggleClass("open-menu hidden");
        jQuery('.hamburger-menu__item_top').toggleClass('j-hamburger-menu__item_top');
        jQuery('.hamburger-menu__item_middle').toggleClass('j-hamburger-menu__item_middle');
        jQuery('.hamburger-menu__item_bottom').toggleClass('j-hamburger-menu__item_bottom');
    });

}