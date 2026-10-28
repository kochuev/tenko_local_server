var isLeftScrollableDrag = isRightScrollableDrag = false;
var point = null;
jQuery(document).ready(function () {
    tabs();
    sliderRange();
    quantity();
    resize();
    if (jQuery('*').is('.highcharts-js')) {
        createTemperatureChart();
        // addPanFunctional();
        // yearChart();
    }

    if (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {
        jQuery('.temperature-chart').removeClass('j-temperature-chart');
    }



    var chart = jQuery('#temperature').highcharts();
    var scrollingContainer = chart.scrollingContainer;
    scrollingContainer.addEventListener('mousemove', () => {
        checkMask();
    });
    scrollingContainer.addEventListener('touchmove', () => {
        checkMask();
    });
    function checkMask() {
        if (scrollingContainer.scrollLeft > 1) {
            jQuery('#temperature').addClass('mask-visible')
        }
        else{
            jQuery('#temperature').removeClass('mask-visible')
        }
    }
    jQuery(".error__header").on("click", function() {
        jQuery(this).closest('.connection-error').find('.error__content').slideToggle();
        jQuery(this).children('.error-toggle-btn').toggleClass('rotate');
    });

});

function checkScrollableDrag(chart, e) {
    const container = chart.scrollingContainer,
        { chartX } = e,
        sBox = chart.scrollablePlotBox,
        { scrollLeft, clientWidth } = container;
    const viewPortPosition = chartX - scrollLeft;
    isRightScrollableDrag = (clientWidth - viewPortPosition - sBox.x) < 50;
    isLeftScrollableDrag = (viewPortPosition - sBox.x) < 50;
}

// function move(container, step) {
//     if (point) {
//         point.chartX += step;
//         if (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {
//             container.dispatchEvent(new TouchEvent("touchmove", point));
//         } else {
//             container.dispatchEvent(new MouseEvent("mousemove", point));
//         }
//     }
// }

// function initUnMoveDrag(chart) {
//     (function unMoveDragStep() {
//         setTimeout(function () {
//             if (isRightScrollableDrag) {
//                 move(chart.container, 4);
//             }
//             if (isLeftScrollableDrag) {
//                 move(chart.container, -4);
//             }
//             requestAnimationFrame(unMoveDragStep)
//         }, 100)
//     })()
// }



// function addPanFunctional() {
//     var chart = jQuery('#temperature').highcharts();
//     var scrollingContainer = chart.scrollingContainer;
//     isPoint = false;
//     let isDown = false;
//     let startX;
//     let scrollLeft;
//     scrollingContainer.addEventListener('mousedown', (e) => {
//         isDown = true;
//         scrollingContainer.classList.add('active');
//         startX = e.pageX - scrollingContainer.offsetLeft;
//         scrollLeft = scrollingContainer.scrollLeft;



//     });
//     scrollingContainer.addEventListener('mouseleave', () => {
//         isDown = false;
//         scrollingContainer.classList.remove('active');

//     });

//     scrollingContainer.addEventListener('mouseup', () => {
//         isDown = false;
//         scrollingContainer.classList.remove('active');

//     });
//     scrollingContainer.addEventListener('mousemove', (e) => {
//         if (!isDown || isPoint) return;
//         e.preventDefault();
//         const x = e.pageX - scrollingContainer.offsetLeft;
//         const walk = (x - startX); //scroll-fast
//         scrollingContainer.scrollLeft = scrollLeft - walk;

//     });

// }

function createTemperatureChart() {
    // jQuery('#temperature').highcharts({
    //     chart: {
    //         type: 'scatter',
    //         renderTo: 'temperature',
    //         animation: false,
    //         spacingTop: 20,
    //         scrollablePlotArea: {
    //             minWidth: 1500,
    //             opacity: 0,
    //           },
    //         findNearestPointBy: 'x',

    //         events: {
    //             render: function () {
    //                 var newArray = this.series[0].data.map(function (el) {
    //                     return Math.floor(el.category);
    //                 });
    //                 for (var i = 0; i < newArray.length - 1; i++) {
    //                     if (newArray.indexOf(newArray[i], i + 1) > -1) {
    //                         jQuery("#interval-error").show();
    //                         break;
    //                     } else {
    //                         jQuery("#interval-error").hide();
    //                     }
    //                 }
    //             },
    //         }
    //     },
    //     title: {
    //         text: ''
    //     },
    //     tooltip: {
    //         enabled: false,
    //     },
    //     plotOptions: {
    //         column: {
    //             colorByPoint: true,
    //         },
    //         series: {
    //             point: {
    //                 events: {
    //                     drag: function (e) {
    //                         var chart = this.series.chart,
    //                             x = e.newPoint && e.newPoint.x,
    //                             px = this.series.xAxis.toPixels(x),
    //                             sLeft = chart.scrollingContainer.scrollLeft,
    //                             sBox = chart.scrollablePlotBox,
    //                             panZone = 50,
    //                             offRight = Math.max(
    //                                 0,
    //                                 (px - sBox.x + panZone) - (sLeft + sBox.width)),
    //                             offLeft = Math.max(
    //                                 0,
    //                                 sLeft - (px - sBox.x - panZone));
    //                         off = offRight || -offLeft;
    //                         point = e.event;
    //                         checkScrollableDrag(chart, e);
    //                         if (off) {
    //                             chart.scrollingContainer.scrollLeft += off;
    //                         }
    //                         var chart_category = this.category;
    //                         isPoint = true;
    //                         var tmp_point = 0;
    //                         chart.series[0].data.forEach(function (entry) {
    //                             if (Math.floor(entry.x) == Math.floor(chart_category)) {
    //                                 tmp_point++;
    //                             }
    //                         });
    //                         if (tmp_point >= 2) {
    //                             jQuery("#interval-error").show();

    //                         } else {
    //                             jQuery("#interval-error").hide();
    //                         }
    //                         jQuery('body').addClass('hidden');




    //                         if (chart.scrollingContainer.scrollLeft > 1) {
    //                             jQuery('#temperature').addClass('mask-visible')
    //                         }
    //                         else{
    //                             jQuery('#temperature').removeClass('mask-visible')
    //                         }
    //                     },

    //                     drop: function (e) {
    //                         var chart = this.series.chart;
    //                         chart.hoverPoint = null;
    //                         chart.hoverPoints = [];
    //                         chart.hoverSeries && chart.hoverSeries.onMouseOut();
    //                         isPoint = isRightScrollableDrag = false;
    //                         point = null;
    //                         jQuery('body').removeClass('hidden');
    //                     },
    //                     click: function () {
    //                         isPoint = isRightScrollableDrag = false;
    //                         point = null;
    //                         if (jQuery('.highcharts-container').is('.remove-point-mode')) {
    //                             this.remove();
    //                         }
    //                     },
    //                 }
    //             },
    //             stickyTracking: false,
    //             marker: {
    //                 fillColor: '#FFFFFF',
    //                 lineWidth: 1,
    //                 lineColor: '',
    //                 radius: 12,
    //                 states: {
    //                     hover: {
    //                         // enabled: false
    //                     }
    //                 }
    //             },
    //             dataLabels: {
    //                 enabled: true,
    //                 valueSuffix: '°C',
    //                 formatter: function () {
    //                     if (parseFloat(this.y).toFixed(0) >= 7) {
    //                         return Math.floor(this.x) + ':00 ; ' + Math.floor(this.y) + ' °C';
    //                     }
    //                     return 'Вимк';
    //                 },
    //                 x: 0,
    //                 y: -15,
    //                 shadow: false,
    //                 style: {
    //                     color: '#555770',
    //                     fontSize: '14px',
    //                     fontWeight: '400',
    //                     fontFamily: '"Rubik", sans-serif',
    //                     textOutline: 'none'
    //                 }
    //             },
    //         },
    //     },

    //     xAxis: {
    //         min: 0,
    //         max: 24,
    //         labels: {
    //             format: '{value}:00',
    //             style: {
    //                 color: '#C7C8D9',
    //                 fontSize: '16px',
    //                 fontFamily: '"Rubik", sans-serif',
    //             },

    //         },
    //     },

    //     yAxis: {
    //         title: {
    //             text: ''
    //         },
    //         tickPositions: [0, 7, 10, 20, 30, 40],
    //         min: 0,
    //         max: 40,
    //         labels: {
    //             formatter: function () {
    //                 var label = this.axis.defaultLabelFormatter.call(this);
    //                 if (label == 7) {
    //                     return `<span style="color:#F53838" >${label}°C</span>`;
    //                 }
    //                 if (label == 0) {
    //                     return `<span style="color:#C7C8D9" >Вимк.</span>`;
    //                 }
    //                 return `${label}°C`;
    //             },
    //             style: {
    //                 color: '#555770;',
    //                 fontSize: '14px',
    //                 fontFamily: '"Rubik", sans-serif',
    //             },
    //         },

    //         plotBands: [{
    //             from: 0,
    //             to: 7,
    //             color: '#BDBDC5',
    //         },
    //         {
    //             from: 7,
    //             to: 100,
    //             color: '#F9F9FB',
    //         }],
    //         stackLabels: {
    //             enabled: true,
    //             format: '{total} кВт',
    //             style: {
    //                 fontWeight: '400',
    //                 color: '#8E90A6',
    //                 fontSize: '12px',
    //                 fontFamily: '"Rubik", sans-serif',
    //             },
    //         }
    //     },

    //     series: [{
    //         data: [0, 1, 2, 3, 4, 5, 20, 7, 15, 20, 14, 7],
    //         type: 'scatter',
    //         cursor: 'move',
    //         dragDrop: {
    //             draggableY: true,
    //             dragSensitivity: 0,
    //             dragMaxY: 40,
    //             dragMinY: 0,
    //             draggableX: true,
    //             dragMaxX: 23,
    //             dragMinX: 0
    //         },
    //         zones: [{
    //             value: 0,
    //             color: '#313246'
    //         }, {
    //             value: 7,
    //             color: '#313246'
    //         }, {
    //             color: '#F53838'
    //         }]
    //     }],
    //     legend: {
    //         enabled: false,
    //     },
    //     credits: {
    //         enabled: false
    //     },
    // });
    // chartjs = jQuery('#temperature').highcharts();
    // initUnMoveDrag(chartjs);
    // var arrayLocation = 1;
    // var increasingValue = 34;
    // var series = chartjs.series[0];

    // jQuery("#add-point").on('click', function () {
    //     if (chartjs.series[0].points.length > 24) {
    //         jQuery('#max-points-error').show();
    //         setTimeout(function () {
    //             jQuery('#max-points-error').hide();
    //         }, 3000);

    //     } else {
    //         series.addPoint({ x: arrayLocation, y: increasingValue });
    //         arrayLocation = arrayLocation + 0.1;
    //     }
    // });


    // jQuery('#copy-day-btn').on('click', function () {
    //     jQuery('.right-nav-top').toggleClass('show-copy-panel');
    //     isShowCopyPanel();
    // });

    // jQuery('#remove-point').on('click', function () {
    //     jQuery('.highcharts-container').toggleClass("remove-point-mode");
    //     jQuery(this).toggleClass("remove-point-mode");

    //     if (jQuery('.highcharts-container').is('.remove-point-mode')) {
    //         jQuery('#add-point').hide();

    //         chartjs.update({
    //             plotOptions: {
    //                 series: {
    //                     marker: {
    //                         symbol: 'url(./img/remove-point-icon.svg)',
    //                     },
    //                 },
    //             },
    //             series: [{
    //                 draggableY: false,
    //                 draggableX: false,

    //             }],
    //         });
    //     } else {
    //         jQuery('#add-point').show();
    //         chartjs.update({
    //             plotOptions: {
    //                 series: {
    //                     marker: {
    //                         symbol: '',
    //                     },
    //                 },
    //             },
    //             series: [{
    //                 draggableY: true,
    //                 draggableX: true,

    //             }],
    //         });
    //     }
    // });

    // // jQuery('input[type=radio][name=chart-switch]').change(function () {
    // //     if (this.value == 'day-switch') {
    // //         chartjs.series[0].setData([0, 1, 2, 3, 4, 5, 20, 7, 15, 20, 14, 7]);
    // //         jQuery('.copy-day').hide();
    // //         jQuery('#copy-day-btn').hide();
    // //         jQuery('#expand-chart').appendTo('.right-nav-bottom');
    // //         jQuery('.right-nav-top').removeClass('is-week');
    // //         jQuery('.copy-day-to').hide();
    // //         jQuery('.copy-btn-wrap').hide();
    // //         jQuery('#add-point').show();
    // //         jQuery('#remove-point').show();
    // //     } else if (this.value == 'week-switch') {
    // //         chartjs.series[0].setData([5, 16, 10]);
    // //         jQuery('.copy-day').show();
    // //         jQuery('#copy-day-btn').show();
    // //         jQuery('#expand-chart').appendTo('.right-nav-top');
    // //         jQuery('.right-nav-top').addClass('is-week');
    // //         isShowCopyPanel();
    // //     }
    // // });

    // jQuery('input[type=radio][name=view-switch]').change(function () {
    //     if (this.value == 'graph-switch') {
    //         jQuery('.temperature-chart-wrapper').show();
    //         jQuery('.temperature-point-list').hide();
    //         jQuery('#expand-chart').show();

    //     } else if (this.value == 'list-switch') {
    //         jQuery('.temperature-chart-wrapper').hide();
    //         jQuery('.temperature-point-list').show();
    //         jQuery('#expand-chart').hide();
    //     }
    // });

    // jQuery('.go-to-graph').on('click', function () {
    //     jQuery('body').addClass('full-graph-mode');
    // });
    // jQuery('.back-to-main').on('click', function () {
    //     jQuery('body').removeClass('full-graph-mode');
    // });

    // function isShowCopyPanel() {
    //     if (jQuery(".right-nav-top").hasClass('show-copy-panel')) {
    //         jQuery('.copy-day-to').show();
    //         jQuery('.copy-btn-wrap').show();
    //         jQuery('#add-point').hide();
    //         jQuery('#remove-point').hide();
    //     } else {
    //         jQuery('.copy-day-to').hide();
    //         jQuery('.copy-btn-wrap').hide();
    //         jQuery('#add-point').show();
    //         jQuery('#remove-point').show();
    //     }
    // }
}


function tabs() {
    // jQuery(".tabs__header-item .tab-name").on('click', function () {
    //     jQuery(".tabs__header-item").removeClass("active").eq(jQuery(this).parent('.tabs__header-item').index()).addClass("active");
    //     jQuery(".tab__item").hide().eq(jQuery(this).parent('.tabs__header-item').index()).fadeIn()
    // }).eq(0).addClass("active");

    jQuery(".info__header-item").on('click', function () {
        jQuery(".info__header-item").removeClass("active").eq(jQuery(this).index()).addClass("active");
        jQuery(".info__item").hide().eq(jQuery(this).index()).fadeIn()
    }).eq(0).addClass("active");
}

function sliderRange() {
    jQuery('[type="range"]').each(function () {
        var curVal = jQuery(this).val();
        jQuery(this).on('change input', function () {
            curVal = jQuery(this).val();
            jQuery(this).closest('.slider-wrapper').find('.temperature-value').html(curVal);
        });
        curVal = jQuery(this).val();
        jQuery(this).closest('.slider-wrapper').find('.temperature-value').html(curVal);
        var maxValue = jQuery(this).prop('max');
        var minValue = jQuery(this).prop('min');
        jQuery(this).closest('.slider-wrapper').find('.range-slider-min').html(minValue);
        jQuery(this).closest('.slider-wrapper').find('.range-slider-max').html(maxValue);
    });
}

function quantity() {
    jQuery('<div class="quantity-nav"><div class="quantity-button quantity-up"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">\n' +
        '<path d="M8.00048 7.21855L4.70048 10.5186L3.75781 9.57589L8.00048 5.33322L12.2431 9.57589L11.3005 10.5186L8.00048 7.21855Z" fill="#8E90A6"/>\n' +
        '</svg>\n</div><div class="quantity-button quantity-down"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">\n' +
        '<path d="M8.00048 8.78145L11.3005 5.48145L12.2431 6.42411L8.00048 10.6668L3.75781 6.42411L4.70048 5.48145L8.00048 8.78145Z" fill="#8E90A6"/>\n' +
        '</svg>\n</div></div>').insertAfter('.quantity-input-wrap');
    jQuery('.quantity').each(function () {
        var spinner = jQuery(this),
            input = spinner.find('input[type="number"]'),
            btnUp = spinner.find('.quantity-up'),
            btnDown = spinner.find('.quantity-down'),
            min = input.attr('min'),
            max = input.attr('max');
        var inputStep = +input.attr('step');
        var inputStepEnd = parseFloat(inputStep.toFixed(1))


        btnUp.click(function () {
            var oldValue = parseFloat(input.val());
            if (oldValue >= max) {
                var newVal = oldValue;
            } else {
                var newVal = oldValue + inputStep;
            }
            spinner.find("input").val(parseFloat(newVal.toFixed(1))).trigger('input');
            spinner.find("input")[0].dispatchEvent(new CustomEvent('input'));
            spinner.find("input").trigger("change");
        });

        btnDown.click(function () {
            var oldValue = parseFloat(input.val());
            if (oldValue <= min) {
                var newVal = oldValue;
            } else {
                var newVal = oldValue - inputStep;
            }
            spinner.find("input").val(parseFloat(newVal.toFixed(1))).trigger('input');
            spinner.find("input")[0].dispatchEvent(new CustomEvent('input'));
            spinner.find("input").trigger("change");
        });

    });
}

function resize() {
    jQuery(window).on('resize', function () {
        var ww = jQuery(window).width();
        var wh = jQuery('body').height();
        var pageScale = ww / 1920;
        var scaleHeight = wh * pageScale;
        console.log("RESIZE DEBUG");
        if (jQuery(window).width() > 900) {
            jQuery(".errors_block").prependTo('.p-temperature__data');

            jQuery('#expand-chart').on('click', function (e) {
                e.preventDefault();

                app.graph_modal_open = true;
                jQuery('#highcharts-modal').fadeTo( 500, 1 );
                jQuery('body').addClass('hidden');
                // console.log("debug 6655");
                jQuery('.temperature-tab-item-inner').appendTo('.modal-content');
            });

            jQuery('.close-modal').on('click', function (e) {
                e.preventDefault();

                app.graph_modal_open = false;
                jQuery.when(jQuery('#highcharts-modal').fadeOut(300))
                    .done(function() {
                        jQuery('body').removeClass('hidden');
                        jQuery('.temperature-tab-item-inner').appendTo('.temperature-tab-item');
                    });
            });
            if (jQuery(window).width() <= 1920) {
                jQuery('.main, .modal-content').css('transform', 'scale(' + pageScale + ')');
                jQuery('.main').height(scaleHeight);
                jQuery('.apply-btn').appendTo('.p-temperature__heating');
                jQuery('.settings-apply-btn').appendTo('.settings-top');
                jQuery('body').removeClass('full-graph-mode');
                jQuery('.sidebar').prependTo('.main');
                jQuery('body').removeClass('information-mode');
            } else {
                jQuery('.main').addClass('main--full');
                jQuery('.modal-content').css('transform', 'unset');
                jQuery('.modal-content').css('position', 'relative');

            }

        } else {
            jQuery(".errors_block").prependTo('.info__content');

            // jQuery('.footer-information-link').on('click', function (e) {
            //     e.preventDefault();
            //     jQuery('body').removeClass().addClass('information-mode');
            // });

            // jQuery('.footer-settings-link').on('click', function (e) {
            //     e.preventDefault();
            //     jQuery('body').removeClass().addClass('settings-mode');

            // });
            
            // jQuery('.footer-temperature-link').on('click', function () {
            //     jQuery('body').removeClass().addClass('temperature-mode');
            // });

            jQuery('.toggle-year-graph-arrow').on('click', function (e) {
                e.preventDefault();
                jQuery(this).toggleClass('rotate').closest('.t-statistics__chart').find('.year-chart-wrapper').stop().slideToggle();
            });

            jQuery('#expand-chart').on('click', function (event) {
                event.preventDefault();
                jQuery('#highcharts-modal').hide();
                jQuery('body').removeClass('hidden');
                jQuery('.temperature-tab-item-inner').appendTo('.temperature-tab-item');
            });

            jQuery('.main, .modal-content').css({ 'transform': 'scale(' + 1 + ')', 'height': 'auto', });
            jQuery('.apply-btn').appendTo('.p-temperature');
            jQuery('.settings-apply-btn').appendTo('.settings-content');
            jQuery('.sidebar').appendTo('.mobile-menu');
        }
    });
    jQuery(window).trigger('resize');
}


