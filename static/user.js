$(function() {
  $(".btn").click(
    function() {
      var imgtovara = $(this).attr('data-imgtovara');
      var nametitle = $(this).attr('data-nametitle');
      var pricetovar = $(this).attr('data-pricetovar');

      $(".tovarimg").append('<img class="img-fluid" src="' + imgtovara + '" alt="..." />');
      $(".tovarinfo").append('<p class="h3">' + nametitle + '</h1>');
      $(".tovarinfo").append('<p><strong>Цена</strong>:' + pricetovar + '</p>');
      $("#hide1").attr('value', nametitle);
      $("#hide2").attr('value', pricetovar);
    })
});